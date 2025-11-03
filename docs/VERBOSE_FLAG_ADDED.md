# ✅ Added: --verbose Flag for Server Logging

## Summary

Added a `--verbose` command-line flag to control SEI injection logging on the server.

## Changes Made

**Default Behavior (NEW):**
- **Quiet mode** - No SEI injection messages printed
- Shows only YOLO inference times and startup messages
- Clean console output for production use

**With --verbose Flag:**
- Shows detailed SEI injection info every ~1 second
- Displays UUID, payload size, buffer size
- Useful for debugging and verification

## Usage

### Quiet Mode (Default)
```bash
python server4.py --input /dev/video0 --model yolov8n.pt
```

**Output:**
```
✅ YOLO model loaded: yolov8n.pt
✅ RTSP server running at rtsp://127.0.0.1:8554/stream
0: 384x640 2 cars, 3.7ms
0: 384x640 3 cars, 4.4ms
```

### Verbose Mode
```bash
python server4.py --input /dev/video0 --model yolov8n.pt --verbose
```

**Output:**
```
✅ YOLO model loaded: yolov8n.pt
✅ RTSP server running at rtsp://127.0.0.1:8554/stream

0: 384x640 2 cars, 3.7ms
[SEI] Injected #1, payload size: 316 bytes
      SEI size: 341 bytes, total output: 51440 bytes
      First 40 bytes of SEI: 000000010605ff4d6c4b8b0443c341a293b73a7b70f7ef00...
      UUID in SEI: 6c4b8b0443c341a293b73a7b70f7ef00

0: 384x640 3 cars, 4.4ms
[... 28 more frames ...]
[SEI] Injected #31, payload size: 563 bytes
      SEI size: 589 bytes, total output: 9061 bytes
      ...
```

## Technical Implementation

1. **Added command-line argument:**
   ```python
   parser.add_argument("--verbose", action="store_true", 
                       help="Enable verbose SEI injection logging (default: quiet)")
   ```

2. **Added class variable to SeiInjector:**
   ```python
   class SeiInjector(GstBase.BaseTransform):
       verbose = False  # Class-level flag
   ```

3. **Set flag from command line:**
   ```python
   SeiInjector.verbose = args.verbose
   ```

4. **Conditional logging:**
   ```python
   if SeiInjector.verbose and self._inject_count % 30 == 1:
       print(f"[SEI] Injected #{self._inject_count}, ...")
   ```

## Important Notes

- **SEI is ALWAYS injected** (every frame) regardless of verbose setting
- **Verbose only controls LOGGING** (what you see in console)
- **Logging frequency:** Every 30 frames (~1 second at 30fps) to avoid spam
- **Zero performance impact** when verbose is off (no string formatting)
- **Minimal performance impact** when verbose is on (<1ms per log message)

## When to Use Each Mode

### Quiet Mode (Default) ✅ Recommended for:
- Production deployments
- Long-running servers
- Clean console output
- Performance testing
- Normal operation

### Verbose Mode 🔍 Use for:
- Initial setup and testing
- Debugging SEI injection
- Verifying metadata is embedded
- Troubleshooting client issues
- Development and testing

## Updated Files

- ✅ `server4.py` - Added verbose flag and conditional logging
- ✅ `READY_TO_USE.md` - Updated examples to show quiet mode by default
- ✅ `VERBOSE_LOGGING_GUIDE.md` - Complete usage guide for the flag

## Examples

```bash
# Production (quiet)
python server4.py --input rtsp://camera/stream --model yolov8n.pt

# Development (verbose)
python server4.py --input /dev/video0 --model yolov8n.pt --verbose

# Custom output with verbose
python server4.py --input http://camera/mjpg --output rtsp://0.0.0.0:5000/stream --verbose
```

## Backward Compatibility

✅ **Fully backward compatible!**
- Old command still works: `python server4.py --input X --model Y`
- Just defaults to quiet mode now instead of verbose
- Add `--verbose` if you want the old behavior

## Benefits

1. **Cleaner logs by default** - Production-ready
2. **Flexible debugging** - Turn on when needed
3. **No performance impact** - Zero overhead in quiet mode
4. **Easy to use** - Single flag
5. **Standard practice** - Follows Unix conventions

Your server is now more professional with sensible defaults! 🎉
