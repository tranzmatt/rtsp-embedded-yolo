# RTSP Video Stream with Embedded YOLO Detections

Real-time object detection streaming over RTSP with metadata embedded as H.264 SEI NAL units.

## 🚀 Quick Start

### Start the Server
```bash
python server.py --input http://camera/stream --model yolov8n.pt
```

### Start the Client
```bash
python client_sei.py --input rtsp://127.0.0.1:8554/stream
```

**That's it!** The client will display YOLO detections in real-time:
```
[frame 0] 2 detections:
  - car 0.84 [231.2, 345.6, 567.8, 678.9]
  - person 0.89 [123.4, 234.5, 345.6, 456.7]
```

## 📁 Project Structure

```
.
├── server.py              # RTSP server with SEI injection
├── client_sei.py          # RTSP client with SEI extraction
├── READY_TO_USE.md         # Detailed quick start guide
├── README.md               # This file
├── yolov8n.pt              # YOLO model (auto-downloaded)
│
├── utils/                  # Diagnostic and debug tools
│   ├── client_sei_debug.py      # Client with verbose debugging
│   ├── test_direct_injection.py  # Test SEI injector directly
│   └── server_options.py         # Alternative configurations
│
└── docs/                   # Documentation
    ├── TROUBLESHOOTING.md        # Detailed troubleshooting
    ├── VERBOSE_LOGGING_GUIDE.md  # Server logging options
    ├── FINAL_SUCCESS.md          # Complete explanation
    └── ... (other guides)
```

## 🎯 What This Does

1. **Server**: Captures video → Runs YOLO detection → Embeds results in H.264 SEI → Streams via RTSP
2. **Client**: Receives RTSP → Extracts SEI metadata → Displays video + detections

**Key Feature:** Metadata travels **inside** the video stream, perfectly synchronized with frames.

## 💻 Requirements

```bash
# GStreamer (Ubuntu/Debian)
sudo apt-get install python3-gi gstreamer1.0-tools gstreamer1.0-plugins-{base,good,bad,ugly} \
                     gir1.2-gst-rtsp-server-1.0 gstreamer1.0-libav

# Create a venv with system site packages available
/usr/bin/python3 -m venv venv

# Activate venv
. ./venv/bin/activatee

# Python packages
pip install -r requirements

```

## 📖 Usage Examples

### Basic Usage
```bash
# Webcam
python server.py --input /dev/video0 --model yolov8n.pt

# IP Camera
python server.py --input rtsp://192.168.1.100/stream --model yolov8n.pt

# MJPEG Stream
python server.py --input http://camera/mjpg/video.mjpg --model yolov8n.pt

# Video File
python server.py --input /path/to/video.mp4 --model yolov8n.pt
```

### Different YOLO Models
```bash
# Nano (fastest)
--model yolov8n.pt

# Small (balanced)
--model yolov8s.pt

# Medium (more accurate)
--model yolov8m.pt
```

### Verbose Logging
```bash
# Show SEI injection details
python server.py --input /dev/video0 --model yolov8n.pt --verbose
```

### Custom RTSP Output
```bash
python server.py --input /dev/video0 --output rtsp://0.0.0.0:5000/yolo
```

## 🔧 Debug Tools (in utils/)

### Test SEI Injection Directly
```bash
python utils/test_direct_injection.py
```
Tests SEI injection without RTSP to isolate issues.

### Debug Client with Detailed Output
```bash
python utils/client_sei_debug.py --input rtsp://127.0.0.1:8554/stream --debug-sei
```
Shows detailed SEI parsing information.

## 📚 Documentation (in docs/)

- **READY_TO_USE.md** - Quick start with examples
- **TROUBLESHOOTING.md** - Common issues and solutions
- **VERBOSE_LOGGING_GUIDE.md** - Server logging options
- **FINAL_SUCCESS.md** - Complete technical explanation
- **ACTION_PLAN.md** - Development history and debugging process

## 🎬 Complete Example

```bash
# Terminal 1 - Start server with webcam
python server.py --input /dev/video0 --model yolov8n.pt

# Output:
# ✅ YOLO model loaded: yolov8n.pt
# ✅ RTSP server running at rtsp://127.0.0.1:8554/stream
# 0: 384x640 2 cars, 1 person, 3.7ms

# Terminal 2 - Start client
python client_sei.py --input rtsp://127.0.0.1:8554/stream

# Output:
# ✅ Connected to rtsp://127.0.0.1:8554/stream
# [frame 0] 3 detections:
#   - car 0.84 [231.2, 345.6, 567.8, 678.9]
#   - car 0.76 [789.0, 890.1, 901.2, 012.3]
#   - person 0.89 [123.4, 234.5, 345.6, 456.7]
```

## ⚙️ How It Works

### Server Pipeline
```
Video Source → OpenCV Capture → YOLO Detection → 
→ x264 Encoding → SEI Injection → h264parse → 
→ RTP Packaging → RTSP Server
```

### Client Pipeline
```
RTSP Client → RTP Depackaging → h264parse → 
→ SEI Extraction + Video Decode → Display
```

### SEI Structure
```
Start Code:    00 00 00 01
NAL Header:    06 (SEI)
Payload Type:  05 (user_data_unregistered)
UUID:          6c4b8b04-43c3-41a2-93b7-3a7b70f7ef00
JSON Data:     {"v":1,"frame":0,"yolo":[...]}
```

## 🚨 Common Issues

### Client shows video but no detections
1. Check server is running with `--verbose` to verify SEI injection
2. Try debug client: `python utils/client_sei_debug.py --debug-sei`
3. See `docs/TROUBLESHOOTING.md` for detailed solutions

### "Cannot open input"
- Check video source URL/path is correct
- For cameras, ensure they're not already in use
- Try with a video file first to test setup

### Poor performance
- Use smaller model: `--model yolov8n.pt` (fastest)
- Reduce resolution in server.py (line 248: change 1280x720)
- Check CPU/GPU usage

## 📊 Performance

Typical performance on modern hardware:
- **YOLO inference:** 3-5ms per frame (yolov8n on CPU)
- **Encoding overhead:** ~2-3ms per frame
- **Network latency:** <100ms local network
- **Total latency:** ~200-300ms end-to-end

## 🔬 Technical Details

- **Video codec:** H.264 (byte-stream format, Annex-B)
- **Metadata format:** SEI user_data_unregistered (NAL type 6, payload type 5)
- **Protocol:** RTSP over RTP
- **Synchronization:** Frame-perfect (SEI embedded in same AU as video)
- **Client compatibility:** Any client that preserves SEI NAL units

## 🤝 Integration

The client code can be integrated into larger applications:

```python
from client_sei import extract_sei_json

# Your GStreamer pipeline
pipeline = Gst.parse_launch("...")
appsink = pipeline.get_by_name("sei_sink")

def on_sample(sink):
    sample = sink.emit("pull-sample")
    buf = sample.get_buffer()
    ok, mapinfo = buf.map(Gst.MapFlags.READ)
    if ok:
        data = bytes(mapinfo.data)
        for metadata in extract_sei_json(data):
            # Process YOLO detections
            frame_id = metadata['frame']
            detections = metadata['yolo']
            # ... your logic here ...
    return Gst.FlowReturn.OK
```

## 📝 License

This is a demonstration project. Adapt as needed for your use case.

## 🎉 Credits

Built using:
- **GStreamer** - Multimedia framework
- **Ultralytics YOLO** - Object detection
- **OpenCV** - Video processing

## 📞 Support

If you encounter issues:
1. Check `READY_TO_USE.md` for quick start
2. Review `docs/TROUBLESHOOTING.md` for common problems
3. Run with `--verbose` to see detailed logs
4. Use `utils/test_direct_injection.py` to test components

---

**Ready to use!** See `READY_TO_USE.md` for more examples and options.
