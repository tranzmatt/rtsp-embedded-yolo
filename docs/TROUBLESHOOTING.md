# SEI Metadata Not Appearing - DIAGNOSIS & FIXES

## Problem Identified

Your client debug output showed:
```
First 100 bytes (hex): 000000020910...
```

The issue: **`00 00 00 02` is NOT a valid H.264 start code!**

Valid start codes are:
- `00 00 00 01` (4-byte Annex-B)
- `00 00 01` (3-byte Annex-B)

The `00 00 00 02` prefix indicates **AVC/length-prefixed format** instead of **Annex-B/byte-stream format**.

## Why This Matters

Your SEI extraction code looks for start codes (`\x00\x00\x00\x01\x06`) to find SEI NAL units. If the data is in length-prefixed format, there are no start codes, so SEI units are never found!

## Root Cause

The issue occurs in the RTSP transmission chain:

1. **Server**: x264enc outputs byte-stream (with start codes) ✅
2. **Server**: SEI injector adds SEI in byte-stream format ✅  
3. **Server**: rtph264pay packetizes for RTP (may convert format) ⚠️
4. **Network**: RTP transmission
5. **Client**: rtph264depay reconstructs H.264 (format depends on caps) ⚠️
6. **Client**: Your parser expects byte-stream with start codes ✅

The problem is in steps 3-5: the format conversion during RTP transmission.

## Fixes Applied

### Fix 1: Client Pipeline - Force Byte-Stream Format

**Old client pipeline:**
```python
rtspsrc ! rtph264depay ! h264parse ! appsink
```

**New client pipeline:**
```python
rtspsrc ! rtph264depay ! 
  video/x-h264,stream-format=byte-stream,alignment=au !
  h264parse config-interval=-1 !
  video/x-h264,stream-format=byte-stream,alignment=au !
  appsink
```

**Key changes:**
- Explicit caps after `rtph264depay` to request byte-stream format
- `config-interval=-1` on `h264parse` (don't insert extra SPS/PPS)
- Explicit caps after `h264parse` to ensure byte-stream output

### Fix 2: Server Pipeline - Better RTP Aggregation

**Old server rtph264pay:**
```python
rtph264pay pt=96 config-interval=1
```

**New server rtph264pay:**
```python
rtph264pay pt=96 config-interval=1 aggregate-mode=zero-latency
```

**Why:** `aggregate-mode=zero-latency` helps rtph264pay preserve NAL unit boundaries and is less likely to drop SEI units.

## How to Test

### Step 1: Check what format you're actually receiving

```bash
python check_depay_output.py rtsp://127.0.0.1:8554/stream
```

This will show you:
- **Test 1**: What rtph264depay outputs by default
- **Test 2**: What format you get with explicit byte-stream caps

**Expected output:**
```
Test 1: Direct from rtph264depay
  ⚠️  Format: AVC / length-prefixed (length=1234)

Test 2: With h264parse forcing byte-stream  
  ✅ Format: Annex-B / byte-stream (4-byte start code)
```

### Step 2: Test the updated client

```bash
python client_sei4_debug.py --input rtsp://127.0.0.1:8554/stream --debug-sei
```

**Expected output if fixed:**
```
SEI Buffer #1
[SEI Parser] Analyzing 47934 bytes
[SEI Parser] First 100 bytes (hex): 00000001067b22763a312c227473...
                                    ^^^^^^^^^ ^ 
                                    Start code| SEI NAL type
[SEI Parser] Found NAL type 6 at offset 0
[SEI Parser] SEI #1, size: 287 bytes
[SEI Parser] ✓ Successfully parsed JSON
[frame 0] 3 detections:
  - person 0.89 [123.4, 234.5, 345.6, 456.7]
```

### Step 3: Verify end-to-end

```bash
# Terminal 1 - Run server with updated code
python server4.py --input /dev/video0 --model yolov8n.pt

# Terminal 2 - Run updated client  
python client_sei4.py --input rtsp://127.0.0.1:8554/stream
```

You should now see YOLO detections printed!

## Alternative Diagnostics

### Dump and analyze raw stream

```bash
# Save 5 seconds of stream
python save_h264.py rtsp://127.0.0.1:8554/stream test.h264 5

# Analyze offline
python find_sei.py test.h264
```

This bypasses the client entirely and shows you exactly what's in the stream.

### Live stream analysis

```bash
python dump_h264.py rtsp://127.0.0.1:8554/stream
```

Shows all NAL units in real-time as they arrive.

## Common Issues

### Issue: Still getting `00 00 00 02` prefixes

**Cause:** rtph264depay is still outputting AVC format despite caps

**Solution:** Try adding this to the client after rtph264depay:
```python
! h264parse ! video/x-h264,stream-format=byte-stream !
```

The h264parse element should convert any format to byte-stream.

### Issue: Server says "Injected" but still no SEI in stream

**Cause:** rtph264pay might be dropping SEI units

**Solutions to try:**
1. Remove `idr-only=true` to inject on every frame:
   ```python
   f"! {SeiInjector.GST_PLUGIN_NAME} name=sei idr-only=false "
   ```

2. Try different rtph264pay aggregate modes:
   ```python
   "! rtph264pay aggregate-mode=none"  # Don't aggregate at all
   ```

3. Insert h264parse between SEI injector and rtph264pay:
   ```python
   f"! {SeiInjector.GST_PLUGIN_NAME} name=sei "
   "! h264parse ! "
   "! rtph264pay"
   ```

### Issue: SEI found but JSON not extracted

**Cause:** Wrong UUID or malformed SEI structure

**Check:**
```bash
python find_sei.py test.h264 | grep UUID
```

Should show: `UUID: 6c4b8b04-43c3-41a2-93b7-3a7b70f7ef00`

If the UUID is different, your client's regex won't match.

## Technical Deep-Dive

### H.264 Format Comparison

**Annex-B / Byte-Stream Format:**
```
00 00 00 01 | 06 | [SEI payload] | 00 00 00 01 | 65 | [IDR slice]
start code  |NAL |                start code   |NAL |
```

**AVC / Length-Prefixed Format:**
```
00 00 01 2A | 06 | [SEI payload] | 00 00 08 F3 | 65 | [IDR slice]
length=298  |NAL |                length=2291  |NAL |
```

Your parser expects Annex-B! The length-prefix `00 00 01 2A` (298 bytes) is NOT a start code.

### SEI Structure

```
Start Code:    00 00 00 01
NAL Header:    06                      (type=6, SEI)
Payload Type:  05                      (user_data_unregistered) 
Payload Size:  XX                      (variable length encoding)
UUID:          6c4b8b04...ef00         (16 bytes)
JSON Data:     7b22763a31...7d         {"v":1,...}
RBSP Stop:     80
```

### Why RTP Changes Format

RTP doesn't preserve H.264 format:
- Server's x264enc → byte-stream with start codes
- rtph264pay → strips start codes, packetizes
- RTP transmission → just NAL unit payloads
- rtph264depay → reconstructs, may use length-prefix by default
- h264parse → can convert to requested format

## Updated Files

All your scripts have been updated with the fixes:

- ✅ `server4.py` - Updated rtph264pay configuration
- ✅ `client_sei4.py` - Fixed pipeline for byte-stream format
- ✅ `client_sei4_debug.py` - Fixed pipeline + detailed debugging

New diagnostic tools:
- 🔍 `check_depay_output.py` - Shows actual format being received
- 🔍 `dump_h264.py` - Real-time NAL unit analysis  
- 🔍 `save_h264.py` - Save stream to file
- 🔍 `find_sei.py` - Offline SEI extraction from file

## Next Steps

1. Run `check_depay_output.py` to confirm format issue
2. Test updated `server4.py` and `client_sei4_debug.py`
3. If still not working, check `dump_h264.py` output
4. Share the output and we'll debug further!

The fix should work for 99% of cases where the issue is format conversion.
