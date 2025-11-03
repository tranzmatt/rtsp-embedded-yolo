# Server Verbose Logging - Usage Guide

## Quick Reference

### Default (Quiet Mode) - Recommended
```bash
python server4.py --input http://64.191.148.57/mjpg/video.mjpg --model yolov8n.pt
```

**Output:**
```
Loading YOLO model...
✅ YOLO model loaded: yolov8n.pt
✅ RTSP server running at rtsp://127.0.0.1:8554/stream

0: 384x640 2 cars, 39.4ms
0: 384x640 3 cars, 4.4ms
0: 384x640 2 cars, 4.6ms
...
```

### Verbose Mode - For Debugging
```bash
python server4.py --input http://64.191.148.57/mjpg/video.mjpg --model yolov8n.pt --verbose
```

**Output:**
```
Loading YOLO model...
✅ YOLO model loaded: yolov8n.pt
✅ RTSP server running at rtsp://127.0.0.1:8554/stream

0: 384x640 2 cars, 39.4ms
[SEI] Injected #1, payload size: 316 bytes
      SEI size: 341 bytes, total output: 51440 bytes
      First 40 bytes of SEI: 000000010605ff4d6c4b8b0443c341a293b73a7b70f7ef007b2276223a312c2274735f6e73223a31
      UUID in SEI: 6c4b8b0443c341a293b73a7b70f7ef00

0: 384x640 3 cars, 4.4ms
0: 384x640 2 cars, 4.6ms
...
0: 384x640 4 cars, 3.9ms
[SEI] Injected #31, payload size: 563 bytes
      SEI size: 589 bytes, total output: 9061 bytes
      First 40 bytes of SEI: 000000010605ffff456c4b8b0443c341a293b73a7b70f7ef007b2276223a312c2274735f6e73223a
      UUID in SEI: 6c4b8b0443c341a293b73a7b70f7ef00
...
```

## When to Use Verbose Mode

### ✅ Use `--verbose` when:
- Debugging SEI injection issues
- Verifying metadata is being embedded
- Checking payload sizes
- Testing a new setup
- Troubleshooting client not receiving metadata

### ❌ Don't use `--verbose` for:
- Production deployments
- Long-running servers
- Performance testing
- When console output needs to be clean

## Command Line Options

```
usage: server4.py [-h] --input INPUT [--model MODEL] [--output OUTPUT] [--verbose]

YOLO → SEI → single RTSP stream

options:
  -h, --help       show this help message and exit
  --input INPUT    input source (v4l, http, rtsp, udp)
  --model MODEL    YOLO model (default: yolov8n.pt)
  --output OUTPUT  RTSP output URL (default: rtsp://127.0.0.1:8554/stream)
  --verbose        Enable verbose SEI injection logging (default: quiet)
```

## Examples

### Webcam with verbose logging
```bash
python server4.py --input /dev/video0 --model yolov8n.pt --verbose
```

### IP Camera (quiet mode)
```bash
python server4.py --input rtsp://192.168.1.100/stream --model yolov8s.pt
```

### MJPEG stream with verbose logging
```bash
python server4.py --input http://camera/mjpg/video.mjpg --model yolov8n.pt --verbose
```

### Custom RTSP output with verbose
```bash
python server4.py --input /dev/video0 --output rtsp://0.0.0.0:5000/yolo --verbose
```

## What Gets Logged in Verbose Mode

The SEI injector logs every 30 frames (~1 second at 30fps):

1. **Injection count** - Total frames with SEI injected
2. **Payload size** - Size of the JSON metadata
3. **SEI NAL size** - Total size including headers
4. **Output size** - Complete H.264 buffer size
5. **SEI hex preview** - First 40 bytes to verify structure
6. **UUID** - Confirms correct UUID is being used

This information is useful for:
- Verifying SEI is being injected
- Checking metadata size (large payloads may impact performance)
- Debugging format issues
- Confirming UUID matches what client expects

## Performance Impact

**Verbose logging has minimal performance impact:**
- Only logs every 30th frame (not every frame)
- Simple string formatting and printing
- No file I/O or network operations
- Typical overhead: <1ms per log message

The main consideration is console output management, not performance.

## Logging Frequency

- **SEI Injection:** Happens on EVERY frame (1, 2, 3, 4, ...)
- **Verbose Logging:** Only every 30 frames (1, 31, 61, 91, ...)
- **At 30fps:** ~1 log message per second

This balance provides enough information to verify operation without flooding the console.

## Production Recommendation

**For production:** Use quiet mode (no `--verbose` flag)
- Cleaner logs
- Easier to spot actual errors
- Standard output only shows YOLO inference times
- SEI injection still works perfectly

**For development/debugging:** Use `--verbose` flag
- Verify SEI injection is working
- Check metadata sizes
- Confirm UUID is correct
- Debug transmission issues

## Redirecting Output

If you want logs but not on console:

```bash
# Redirect to file
python server4.py --input /dev/video0 --verbose 2>&1 | tee server.log

# Suppress all output
python server4.py --input /dev/video0 > /dev/null 2>&1

# Keep errors, suppress normal output
python server4.py --input /dev/video0 > /dev/null
```

## Summary

- **Default:** Quiet mode - clean console
- **`--verbose`:** Shows SEI injection details every ~1 second
- **Both modes:** SEI is injected on every frame
- **Logging frequency:** Every 30 frames to avoid spam
- **Use verbose:** During setup and debugging
- **Use quiet:** For production and clean logs

Your server is now production-ready with flexible logging! 🎉
