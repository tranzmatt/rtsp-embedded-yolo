# Quick Reference - SEI Metadata Debugging

## 🚨 Problem Identified

Your stream has **AVC/length-prefixed format** (starts with `00 00 00 02`) instead of **Annex-B/byte-stream** (starts with `00 00 00 01`).

Your SEI parser requires Annex-B format with start codes!

## ✅ Fixes Applied

**Updated Files:**
- `server4.py` - Better rtph264pay config
- `client_sei4.py` - Forces byte-stream format
- `client_sei4_debug.py` - Same + debug output

## 🔍 Quick Tests (Run in Order)

### 1. Check Current Format (30 seconds)
```bash
python check_depay_output.py rtsp://127.0.0.1:8554/stream
```
**Look for:** Should see "byte-stream" in Test 2

### 2. Test Updated Client (immediate)
```bash
python client_sei4_debug.py --input rtsp://127.0.0.1:8554/stream --debug-sei
```
**Look for:** `[SEI Parser] Found NAL type 6` and detection output

### 3. Verify Stream Contents (1 minute)
```bash
python save_h264.py rtsp://127.0.0.1:8554/stream test.h264 5
python find_sei.py test.h264
```
**Look for:** `SEI #1 found` and JSON extraction

## 📊 Quick Status Check

Run the updated client and check first buffer:

**❌ STILL BROKEN** - You'll see:
```
First 100 bytes (hex): 000000020910...
                       ^^^^^^^^
                       Not a start code!
```

**✅ FIXED** - You'll see:
```
First 100 bytes (hex): 000000010667...
                       ^^^^^^^^ ^^
                       Start cd| SEI type
[SEI Parser] Found NAL type 6 at offset 0
[frame 0] 3 detections:
```

## 🛠️ If Still Not Working

### Try 1: Disable IDR-only (server4.py line 228)
```python
f"! {SeiInjector.GST_PLUGIN_NAME} name=sei idr-only=false "
```

### Try 2: Different rtph264pay mode (server4.py line 229)
```python
"! rtph264pay aggregate-mode=none pt=96 config-interval=1"
```

### Try 3: Add h264parse in server
```python
f"! {SeiInjector.GST_PLUGIN_NAME} name=sei "
"! h264parse ! "
"! rtph264pay pt=96 config-interval=1"
```

## 📁 All Tools Available

Diagnostic scripts:
- `check_depay_output.py` - What format are you receiving?
- `dump_h264.py` - Live NAL unit viewer
- `save_h264.py` - Save stream to file  
- `find_sei.py` - Offline SEI finder
- `client_sei4_debug.py` - Enhanced client with debugging

Test scripts:
- `test_sei_element.py` - Test SEI injector directly
- `test_sei_injector.py` - Full element test

Guides:
- `TROUBLESHOOTING.md` - Complete technical guide
- `SEI_DEBUGGING_GUIDE.md` - Step-by-step debugging

## 🎯 Most Likely Solution

Run the updated scripts! The client pipeline fix should resolve 90% of cases:

```bash
# Make sure you're using the updated files
python server4.py --input <your_input> --model yolov8n.pt
python client_sei4.py --input rtsp://127.0.0.1:8554/stream
```

## 📝 Report Results

If still not working, run this and share output:
```bash
python check_depay_output.py rtsp://127.0.0.1:8554/stream > format_check.txt
python client_sei4_debug.py --input rtsp://127.0.0.1:8554/stream --debug-sei 2>&1 | head -100 > client_debug.txt
```

Then share `format_check.txt` and `client_debug.txt`!
