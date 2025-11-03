#!/usr/bin/env python3
"""
Alternative server configurations to test SEI preservation
"""

# Configuration options to try (edit launch_string in server4.py)

# OPTION 1: Add h264parse between SEI injector and rtph264pay
# This forces re-parsing which might help rtph264pay see the SEI
OPTION_1 = """
! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=60 byte-stream=true
! video/x-h264,stream-format=byte-stream,alignment=au
! pyseiinjector4 name=sei idr-only=true
! h264parse config-interval=-1
! video/x-h264,stream-format=byte-stream,alignment=au
! rtph264pay name=pay0 pt=96 config-interval=1 aggregate-mode=zero-latency
"""

# OPTION 2: Use rtph264pay with aggregate-mode=none
# Prevents aggregation which might drop SEI
OPTION_2 = """
! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=60 byte-stream=true
! video/x-h264,stream-format=byte-stream,alignment=au
! pyseiinjector4 name=sei idr-only=false
! rtph264pay name=pay0 pt=96 config-interval=1 aggregate-mode=none
"""

# OPTION 3: Inject on every frame (not just IDR)
# Maybe rtph264pay only preserves SEI on certain frames
OPTION_3 = """
! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=60 byte-stream=true
! video/x-h264,stream-format=byte-stream,alignment=au
! pyseiinjector4 name=sei idr-only=false
! rtph264pay name=pay0 pt=96 config-interval=1 aggregate-mode=zero-latency
"""

# OPTION 4: Disable x264 SEI to avoid conflicts
# x264 might be overwriting our SEI
OPTION_4 = """
! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=60 byte-stream=true option-string="no-info=1"
! video/x-h264,stream-format=byte-stream,alignment=au
! pyseiinjector4 name=sei idr-only=true
! rtph264pay name=pay0 pt=96 config-interval=1
"""

# OPTION 5: Maximum SEI preservation (all fixes combined)
OPTION_5 = """
! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=60 byte-stream=true option-string="no-info=1"
! video/x-h264,stream-format=byte-stream,alignment=au
! pyseiinjector4 name=sei idr-only=false
! h264parse config-interval=-1
! video/x-h264,stream-format=byte-stream,alignment=au
! rtph264pay name=pay0 pt=96 config-interval=-1 aggregate-mode=zero-latency
"""

print("SEI Preservation Options for server4.py")
print("="*60)
print("\nTo test each option, replace the launch_string in YoloRTSPFactory.__init__")
print("in server4.py (around line 220-229) with one of these configurations:")
print()

for i, opt in enumerate([OPTION_1, OPTION_2, OPTION_3, OPTION_4, OPTION_5], 1):
    print(f"\n{'='*60}")
    print(f"OPTION {i}:")
    print(opt.strip())
    print()
    if i == 1:
        print("Rationale: h264parse re-analyzes stream, helps rtph264pay see SEI")
    elif i == 2:
        print("Rationale: aggregate-mode=none prevents combining NALs which might drop SEI")
    elif i == 3:
        print("Rationale: Inject on every frame (not just keyframes)")
    elif i == 4:
        print("Rationale: Disable x264's built-in SEI to avoid conflicts")
    elif i == 5:
        print("Rationale: All fixes combined (most likely to work)")

print("\n" + "="*60)
print("Testing procedure:")
print("1. Update server4.py with an option")
print("2. Restart the server")
print("3. Run: python client_sei4_debug.py --input rtsp://... --debug-sei")
print("4. Check if UUID 6c4b8b04-43c3-41a2-93b7-3a7b70f7ef00 appears")
print("\nStart with OPTION 5 (most aggressive) and work backwards.")
