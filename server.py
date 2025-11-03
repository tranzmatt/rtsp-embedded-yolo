#!/usr/bin/env python3
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GLib, GObject, GstRtspServer, GstBase
import cv2
import json
import time
import argparse
import uuid
import numpy as np
from ultralytics import YOLO

# init GStreamer
Gst.init(None)

# ============================================================
# Helper to build H.264 SEI user_data_unregistered
# ============================================================

H264_START_CODE = b"\x00\x00\x00\x01"
SEI_NAL_TYPE = 6  # H.264 SEI

def build_h264_sei_udu(uuid_bytes: bytes, payload: bytes) -> bytes:
    """
    Build an H.264 SEI NAL (user_data_unregistered) that carries `payload`.
    payload should already be e.g. JSON bytes.
    """
    # payload_type = 5 for user_data_unregistered
    pt = 5
    payload_type_bytes = b""
    while pt >= 255:
        payload_type_bytes += b"\xff"
        pt -= 255
    payload_type_bytes += bytes([pt])

    # actual body = uuid(16) + payload
    body = uuid_bytes + payload

    # payload_size
    sz = len(body)
    payload_size_bytes = b""
    while sz >= 255:
        payload_size_bytes += b"\xff"
        sz -= 255
    payload_size_bytes += bytes([sz])

    # rbsp: payload-type + size + body + rbsp stop
    sei_rbsp = payload_type_bytes + payload_size_bytes + body + b"\x80"
    # 1-byte NAL header (nal_unit_type = 6)
    nal_hdr = bytes([SEI_NAL_TYPE])
    return H264_START_CODE + nal_hdr + sei_rbsp


# ============================================================
# SEI-injector element (non-inplace)
# ============================================================

class SeiInjector(GstBase.BaseTransform):
    GST_PLUGIN_NAME = "pyseiinjector4"
    
    # Class variable for verbose logging control
    verbose = False

    __gstmetadata__ = (
        "Python SEI Injector 4",
        "Filter/Video",
        "Inject YOLO JSON as H.264 SEI (user_data_unregistered)",
        "you",
    )

    __gsttemplates__ = (
        Gst.PadTemplate.new(
            "sink",
            Gst.PadDirection.SINK,
            Gst.PadPresence.ALWAYS,
            Gst.Caps.from_string("video/x-h264,stream-format=byte-stream,alignment=au"),
        ),
        Gst.PadTemplate.new(
            "src",
            Gst.PadDirection.SRC,
            Gst.PadPresence.ALWAYS,
            Gst.Caps.from_string("video/x-h264,stream-format=byte-stream,alignment=au"),
        ),
    )

    __gproperties__ = {
        "uuid": (
            GObject.TYPE_STRING,
            "UUID",
            "UUID for user_data_unregistered",
            "6c4b8b04-43c3-41a2-93b7-3a7b70f7ef00",
            GObject.ParamFlags.READWRITE,
        ),
        "idr-only": (
            GObject.TYPE_BOOLEAN,
            "Inject only on IDR frames",
            "If true, inject SEI only when an IDR is seen",
            True,
            GObject.ParamFlags.READWRITE,
        ),
    }

    def __init__(self):
        super().__init__()
        # CRITICAL: We're modifying buffer size (growing it), so not in-place
        self.set_in_place(False)
        self._uuid = uuid.UUID("6c4b8b04-43c3-41a2-93b7-3a7b70f7ef00")
        self._uuid_bytes = self._uuid.bytes
        self._idr_only = True
        # this will be set from outside (server’s capture loop)
        self._latest_json = b"{}"
        self._inject_count = 0  # debug counter

    # allow server to call: sei_element.set_latest_json(...)
    def set_latest_json(self, d: dict):
        self._latest_json = json.dumps(d, separators=(",", ":")).encode("utf-8")

    def do_get_property(self, prop):
        if prop.name == "uuid":
            return str(self._uuid)
        if prop.name == "idr-only":
            return self._idr_only
        return None

    def do_set_property(self, prop, value):
        if prop.name == "uuid":
            self._uuid = uuid.UUID(value)
            self._uuid_bytes = self._uuid.bytes
        elif prop.name == "idr-only":
            self._idr_only = bool(value)

    def _is_idr(self, data: bytes) -> bool:
        """Check if buffer contains an IDR slice (NAL type 5)"""
        pos = 0
        while pos < len(data) - 4:
            # Look for start codes (both 3-byte and 4-byte)
            if data[pos:pos+4] == b"\x00\x00\x00\x01":
                # 4-byte start code
                nal_start = pos + 4
                if nal_start < len(data):
                    nal_type = data[nal_start] & 0x1F
                    if nal_type == 5:  # IDR slice
                        return True
                pos = nal_start
            elif data[pos:pos+3] == b"\x00\x00\x01":
                # 3-byte start code
                nal_start = pos + 3
                if nal_start < len(data):
                    nal_type = data[nal_start] & 0x1F
                    if nal_type == 5:  # IDR slice
                        return True
                pos = nal_start
            else:
                pos += 1
        return False

    def do_prepare_output_buffer(self, inbuf: Gst.Buffer):
        """Pre-allocate output buffer with enough space for SEI + original data"""
        ok, inmap = inbuf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.ERROR, None
        
        original_size = len(inmap.data)
        inbuf.unmap(inmap)
        
        # Estimate max SEI size (UUID + payload + overhead)
        max_sei_size = 16 + len(self._latest_json) + 20
        out_size = original_size + max_sei_size
        
        # Allocate new buffer
        outbuf = Gst.Buffer.new_allocate(None, out_size, None)
        return Gst.FlowReturn.OK, outbuf

    def do_transform(self, inbuf: Gst.Buffer, outbuf: Gst.Buffer):
        # map incoming h264
        ok, inmap = inbuf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.ERROR
        original = bytes(inmap.data)
        inbuf.unmap(inmap)

        inject_now = True
        if self._idr_only:
            inject_now = self._is_idr(original)

        if inject_now and self._latest_json:
            sei = build_h264_sei_udu(self._uuid_bytes, self._latest_json)
            combined = sei + original
            self._inject_count += 1
            if SeiInjector.verbose and self._inject_count % 30 == 1:  # Log every ~1 second at 30fps
                print(f"[SEI] Injected #{self._inject_count}, payload size: {len(self._latest_json)} bytes")
                print(f"      SEI size: {len(sei)} bytes, total output: {len(combined)} bytes")
                print(f"      First 40 bytes of SEI: {sei[:40].hex()}")
                print(f"      UUID in SEI: {self._uuid_bytes.hex()}")
        else:
            combined = original
            if SeiInjector.verbose and self._inject_count == 0 and len(original) > 100:
                # Debug why we're not injecting
                is_idr = self._is_idr(original)
                print(f"[SEI Debug] First buffer - NOT injecting:")
                print(f"            Buffer size: {len(original)}")
                print(f"            _idr_only: {self._idr_only}")
                print(f"            is IDR: {is_idr}")
                print(f"            _latest_json set: {bool(self._latest_json)}")
                print(f"            _latest_json: {self._latest_json[:100] if self._latest_json else 'None'}")

        # Write to output buffer
        outbuf.set_size(len(combined))
        ok, outmap = outbuf.map(Gst.MapFlags.WRITE)
        if not ok:
            return Gst.FlowReturn.ERROR
        outmap.data[:len(combined)] = combined
        outbuf.unmap(outmap)

        # copy timestamps
        outbuf.pts = inbuf.pts
        outbuf.dts = inbuf.dts
        outbuf.duration = inbuf.duration
        outbuf.offset = inbuf.offset
        outbuf.offset_end = inbuf.offset_end
        outbuf.set_flags(inbuf.get_flags())

        return Gst.FlowReturn.OK


GObject.type_register(SeiInjector)
Gst.Element.register(None, SeiInjector.GST_PLUGIN_NAME, 0, SeiInjector)

# ============================================================
# RTSP factory
# ============================================================

def now_ns():
    return time.time_ns()

class YoloRTSPFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, src_url: str, yolo_model):
        super().__init__()
        # OpenCV capture for any source
        self.cap = cv2.VideoCapture(src_url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open input: {src_url}")

        self.yolo = yolo_model
        self.frame_id = 0
        self.duration = 1 / 30 * Gst.SECOND

        # GStreamer pipeline with aggressive SEI preservation
        # appsrc (BGR) -> convert -> I420 -> x264enc (no-info) -> pyseiinjector4 -> h264parse -> rtph264pay
        self.launch_string = (
            "appsrc name=src is-live=true block=true format=GST_FORMAT_TIME "
            "caps=video/x-raw,format=BGR,width=1280,height=720,framerate=30/1 "
            "! videoconvert ! video/x-raw,format=I420 "
            "! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=60 byte-stream=true "
            "option-string=\"nal-hrd=cbr:force-cfr=1\" "
            "! video/x-h264,stream-format=byte-stream,alignment=au "
            f"! {SeiInjector.GST_PLUGIN_NAME} name=sei idr-only=false "
            "! h264parse config-interval=-1 "
            "! video/x-h264,stream-format=byte-stream,alignment=au "
            "! rtph264pay name=pay0 pt=96 config-interval=-1 aggregate-mode=zero-latency"
        )
        self.sei_element = None

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, media):
        pipeline = media.get_element()
        appsrc = pipeline.get_child_by_name("src")
        self.sei_element = pipeline.get_child_by_name("sei")

        # need-data -> capture frame, run yolo, update sei, push frame
        appsrc.connect("need-data", self.on_need_data)

    def on_need_data(self, src, length):
        ok, frame = self.cap.read()
        if not ok:
            # just drop if source stalls
            return
        frame = cv2.resize(frame, (1280, 720))

        # run YOLO on original frame
        results = self.yolo(frame)

        detections = []
        for r in results:
            names = r.names
            for b in r.boxes:
                cls = int(b.cls[0])
                conf = float(b.conf[0])
                xyxy = b.xyxy[0].tolist()
                detections.append(
                    {
                        "cls": cls,
                        "name": names.get(cls, str(cls)),
                        "conf": conf,
                        "xyxy": xyxy,
                    }
                )

        # build metadata for this frame
        meta = {
            "v": 1,
            "ts_ns": now_ns(),
            "frame": self.frame_id,
            "yolo": detections,
        }

        # update SEI element so next encoded h264 buffer gets this JSON
        if self.sei_element is not None:
            self.sei_element.set_latest_json(meta)

        # push ORIGINAL frame
        data = frame.tobytes()
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        ts = self.frame_id * self.duration
        buf.pts = buf.dts = int(ts)
        buf.duration = self.duration
        buf.offset = ts
        self.frame_id += 1

        # make sure caps are set
        caps = Gst.Caps.from_string(
            "video/x-raw,format=BGR,width=1280,height=720,framerate=30/1"
        )
        src.set_caps(caps)
        src.emit("push-buffer", buf)


# ============================================================
# RTSP server wrapper
# ============================================================

class YoloRTSPServer(GstRtspServer.RTSPServer):
    def __init__(self, factory, port=8554, mount="/stream"):
        super().__init__()
        factory.set_shared(True)
        self.set_service(str(port))
        self.get_mount_points().add_factory(mount, factory)
        self.attach(None)
        print(f"✅ RTSP server running at rtsp://127.0.0.1:{port}{mount}")


def main():
    parser = argparse.ArgumentParser(description="YOLO → SEI → single RTSP stream")
    parser.add_argument("--input", required=True, help="input source (v4l, http, rtsp, udp)")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model")
    parser.add_argument(
        "--output",
        default="rtsp://127.0.0.1:8554/stream",
        help="RTSP output URL (rtsp://host:port/path)",
    )
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="Enable verbose SEI injection logging (default: quiet)"
    )
    args = parser.parse_args()
    
    # Set verbose logging for SEI injector
    SeiInjector.verbose = args.verbose

    print("Loading YOLO model...")
    yolo = YOLO(args.model)
    print(f"✅ YOLO model loaded: {args.model}")

    # parse output
    # rtsp://127.0.0.1:8554/stream
    parts = args.output.split("/")
    host_port = parts[2]  # 127.0.0.1:8554
    path = "/" + parts[3] if len(parts) > 3 else "/stream"
    port = int(host_port.split(":")[1])

    factory = YoloRTSPFactory(args.input, yolo)
    server = YoloRTSPServer(factory, port=port, mount=path)

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("Shutting down...")
        loop.quit()


if __name__ == "__main__":
    main()

