#!/usr/bin/env python3
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib
import argparse, re, json, sys, cv2, numpy as np, queue, threading

Gst.init(None)

# -------- SEI extraction --------
def extract_sei_json(data: bytes):
    """Extract SEI JSON with proper nested brace handling"""
    pos = 0
    while pos < len(data) - 4:
        # Look for start codes
        start_4 = data.find(b"\x00\x00\x00\x01", pos)
        start_3 = data.find(b"\x00\x00\x01", pos)
        
        if start_4 == -1 and start_3 == -1:
            break
        
        if start_4 != -1 and (start_3 == -1 or start_4 < start_3):
            nal_start = start_4 + 4
            pos = start_4
        else:
            nal_start = start_3 + 3
            pos = start_3
        
        if nal_start >= len(data):
            break
            
        nal_type = data[nal_start] & 0x1F
        
        if nal_type == 6:  # SEI
            # Find next start code to determine SEI size
            next_4 = data.find(b"\x00\x00\x00\x01", nal_start)
            next_3 = data.find(b"\x00\x00\x01", nal_start)
            
            if next_4 != -1 and (next_3 == -1 or next_4 < next_3):
                sei_end = next_4
            elif next_3 != -1:
                sei_end = next_3
            else:
                sei_end = len(data)
            
            sei_data = data[nal_start:sei_end]
            
            # Parse SEI payload
            idx = 1  # Skip NAL header
            
            # Read payload type
            payload_type = 0
            while idx < len(sei_data) and sei_data[idx] == 0xFF:
                payload_type += 255
                idx += 1
            if idx < len(sei_data):
                payload_type += sei_data[idx]
                idx += 1
            
            # Read payload size
            payload_size = 0
            while idx < len(sei_data) and sei_data[idx] == 0xFF:
                payload_size += 255
                idx += 1
            if idx < len(sei_data):
                payload_size += sei_data[idx]
                idx += 1
            
            # Check if it's user_data_unregistered (type 5)
            if payload_type == 5:
                # Skip UUID (16 bytes)
                if idx + 16 <= len(sei_data):
                    idx += 16
                    
                    # Extract user data
                    user_data = sei_data[idx:idx+payload_size-16]
                    
                    # Extract complete JSON by counting braces
                    json_start = user_data.find(b'{')
                    if json_start != -1:
                        brace_count = 0
                        json_end = json_start
                        for i in range(json_start, len(user_data)):
                            if user_data[i:i+1] == b'{':
                                brace_count += 1
                            elif user_data[i:i+1] == b'}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                        
                        if json_end > json_start:
                            try:
                                json_str = user_data[json_start:json_end].decode('utf-8')
                                meta = json.loads(json_str)
                                yield meta
                            except Exception:
                                pass
        
        pos = nal_start + 1



def main():
    ap = argparse.ArgumentParser(description="RTSP SEI metadata client (safe main-thread loop)")
    ap.add_argument("--input", required=True, help="rtsp:// URL")
    ap.add_argument("--no-video", action="store_true", help="disable video window")
    args = ap.parse_args()

    # Build pipeline - CRITICAL: force byte-stream format with start codes
    pipeline_str = f"""
        rtspsrc location={args.input} latency=0 !
            rtph264depay ! 
            video/x-h264,stream-format=byte-stream,alignment=au !
            h264parse config-interval=-1 !
            video/x-h264,stream-format=byte-stream,alignment=au !
            tee name=t

            t. ! queue !
                appsink name=sei_sink emit-signals=true sync=false

            t. ! queue ! avdec_h264 ! videoconvert !
                video/x-raw,format=BGR !
                appsink name=video_sink emit-signals=true sync=false
    """
    pipeline = Gst.parse_launch(pipeline_str)
    sei_sink = pipeline.get_by_name("sei_sink")
    video_sink = pipeline.get_by_name("video_sink")

    frame_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
    stop_flag = {"run": True}

    # ---------- callbacks ----------
    def on_video_sample(sink):
        sample = sink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        caps = sample.get_caps()
        w = caps.get_structure(0).get_value("width")
        h = caps.get_structure(0).get_value("height")
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if ok:
            frame = np.frombuffer(mapinfo.data, np.uint8).reshape((h, w, 3))
            buf.unmap(mapinfo)
            if not frame_q.full():
                frame_q.put(frame)
        return Gst.FlowReturn.OK

    def on_sei_sample(sink):
        sample = sink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if ok:
            data = bytes(mapinfo.data)
            buf.unmap(mapinfo)
            for meta in extract_sei_json(data):
                frame_id = meta.get("frame")
                yolo = meta.get("yolo", [])
                if yolo:
                    print(f"[frame {frame_id}] {len(yolo)} detections:")
                    for det in yolo:
                        print(f"  - {det.get('name')} {det.get('conf'):.2f} {det.get('xyxy')}")
                    sys.stdout.flush()
        return Gst.FlowReturn.OK

    sei_sink.connect("new-sample", on_sei_sample)
    video_sink.connect("new-sample", on_video_sample)

    # ---------- bus handling ----------
    bus = pipeline.get_bus()
    def on_bus_msg(bus, msg):
        t = msg.type
        if t in (Gst.MessageType.ERROR, Gst.MessageType.EOS):
            err, dbg = msg.parse_error() if t == Gst.MessageType.ERROR else (None, None)
            print(f"GStreamer {t}: {err or 'EOS'} {dbg or ''}")
            stop_flag["run"] = False
            loop.quit()

    bus.add_signal_watch()
    bus.connect("message", on_bus_msg)

    # ---------- run ----------
    pipeline.set_state(Gst.State.PLAYING)
    loop = GLib.MainLoop()
    print(f"✅ Connected to {args.input}")
    print("Press 'q' in window to quit.\n")

    # Display frames using GLib timeout on main thread (only if GUI enabled)
    def on_frame_timeout():
        if not stop_flag["run"]:
            return False  # Stop the timeout
        
        try:
            frame = frame_q.get_nowait()
            cv2.imshow("RTSP Video", frame)
        except queue.Empty:
            pass
        
        # Check for 'q' key press
        if cv2.waitKey(1) & 0xFF == ord("q"):
            stop_flag["run"] = False
            loop.quit()
            return False  # Stop the timeout
        
        return True  # Continue the timeout

    if not args.no_video:
        GLib.timeout_add(30, on_frame_timeout)  # ~30fps display rate

    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        stop_flag["run"] = False
        pipeline.set_state(Gst.State.NULL)
        if not args.no_video:
            cv2.destroyAllWindows()
        print("Shutting down...")

if __name__ == "__main__":
    main()

