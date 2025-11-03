#!/usr/bin/env python3
"""
Test SEI injection by writing directly to file (no RTSP/RTP)
This isolates whether the problem is in the injector or in rtph264pay
"""
import sys
import os

# Import the server module to get the SEI injector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

# Import SEI injector from server
try:
    from server4 import SeiInjector
    print("✅ Imported SeiInjector")
except ImportError as e:
    print(f"❌ Failed to import: {e}")
    print("Make sure server4.py is in the same directory!")
    sys.exit(1)

Gst.init(None)

def test_direct_file_injection():
    """Test SEI injection writing directly to file"""
    print("\n" + "="*60)
    print("Test: SEI Injection to File (bypassing RTSP)")
    print("="*60)
    
    # Pipeline: videotestsrc → x264enc → sei injector → file
    pipeline_str = """
        videotestsrc num-buffers=60 pattern=snow !
        video/x-raw,width=640,height=480,framerate=30/1 !
        x264enc tune=zerolatency key-int-max=30 byte-stream=true !
        video/x-h264,stream-format=byte-stream,alignment=au !
        pyseiinjector4 name=sei idr-only=false !
        filesink location=test_direct.h264
    """
    
    print("Pipeline:")
    print("  videotestsrc → x264enc → pyseiinjector4 → file")
    print()
    
    try:
        pipeline = Gst.parse_launch(pipeline_str)
        print("✅ Pipeline created")
    except Exception as e:
        print(f"❌ Failed to create pipeline: {e}")
        return False
    
    sei = pipeline.get_by_name("sei")
    if not sei:
        print("❌ Could not get SEI element")
        return False
    
    # Set test metadata
    test_meta = {
        "v": 1,
        "frame": 0,
        "test": "direct_file_test",
        "yolo": [
            {"cls": 0, "name": "person", "conf": 0.95, "xyxy": [100, 100, 200, 200]}
        ]
    }
    sei.set_latest_json(test_meta)
    print(f"Set test metadata: {test_meta}")
    print()
    
    # Monitor injection count
    injection_count = [0]
    original_transform = sei.do_transform
    
    def monitored_transform(inbuf, outbuf):
        result = original_transform(inbuf, outbuf)
        if hasattr(sei, '_inject_count'):
            if sei._inject_count > injection_count[0]:
                injection_count[0] = sei._inject_count
                print(f"[Monitor] Injection count now: {injection_count[0]}")
        return result
    
    sei.do_transform = monitored_transform
    
    # Run pipeline
    bus = pipeline.get_bus()
    loop = GLib.MainLoop()
    
    def on_msg(bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print(f"❌ ERROR: {err}")
            loop.quit()
        elif msg.type == Gst.MessageType.EOS:
            print("\n✅ Recording complete")
            loop.quit()
    
    bus.add_signal_watch()
    bus.connect("message", on_msg)
    
    print("Recording 60 frames (2 seconds at 30fps)...")
    pipeline.set_state(Gst.State.PLAYING)
    
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        pipeline.set_state(Gst.State.NULL)
    
    print(f"\nTotal injections reported: {injection_count[0]}")
    
    # Analyze output file
    if not os.path.exists("test_direct.h264"):
        print("❌ Output file not created!")
        return False
    
    print("\n" + "="*60)
    print("Analyzing output file...")
    print("="*60)
    
    with open("test_direct.h264", "rb") as f:
        data = f.read()
    
    print(f"File size: {len(data):,} bytes")
    
    # Find SEI units
    x264_uuid = bytes.fromhex("dc45e9bde6d948b7962cd820d923eeef")
    custom_uuid = bytes.fromhex("6c4b8b0443c341a293b73a7b70f7ef00")
    
    x264_sei_count = 0
    custom_sei_count = 0
    total_sei_count = 0
    
    pos = 0
    while pos < len(data):
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
            total_sei_count += 1
            
            # Find next NAL to get SEI data
            next_4 = data.find(b"\x00\x00\x00\x01", nal_start)
            next_3 = data.find(b"\x00\x00\x01", nal_start)
            
            if next_4 != -1 and (next_3 == -1 or next_4 < next_3):
                sei_end = next_4
            elif next_3 != -1:
                sei_end = next_3
            else:
                sei_end = len(data)
            
            sei_data = data[pos:sei_end]
            
            if x264_uuid in sei_data:
                x264_sei_count += 1
            if custom_uuid in sei_data:
                custom_sei_count += 1
                print(f"\n✅ Found custom SEI #{custom_sei_count} at offset {pos}")
                print(f"   Size: {len(sei_data)} bytes")
                # Try to extract JSON
                json_start = sei_data.find(b'{')
                json_end = sei_data.find(b'}', json_start) + 1 if json_start != -1 else -1
                if json_start != -1 and json_end > json_start:
                    json_data = sei_data[json_start:json_end]
                    print(f"   JSON: {json_data.decode('utf-8', errors='ignore')}")
        
        pos = nal_start + 1
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Total SEI NAL units: {total_sei_count}")
    print(f"  x264 encoder SEI: {x264_sei_count}")
    print(f"  Custom UUID SEI: {custom_sei_count}")
    print(f"  Injections claimed: {injection_count[0]}")
    
    if custom_sei_count > 0:
        print(f"\n✅ SUCCESS! Custom SEI is being injected!")
        print(f"   The problem is in rtph264pay or RTP transmission")
        return True
    elif injection_count[0] > 0:
        print(f"\n⚠️  PARTIAL: Injector claims {injection_count[0]} injections")
        print(f"   But no custom SEI found in output!")
        print(f"   The buffer modification is not working correctly")
        return False
    else:
        print(f"\n❌ FAILURE: Injector not injecting at all")
        return False


if __name__ == "__main__":
    success = test_direct_file_injection()
    
    print("\n" + "="*60)
    if success:
        print("Next step: The injector works! Problem is in rtph264pay.")
        print("Try these fixes in server4.py:")
        print("  1. Remove rtph264pay, use different transmission")
        print("  2. Add h264parse between injector and rtph264pay")
        print("  3. Try rtph264pay aggregate-mode=none")
    else:
        print("The SEI injector itself has issues.")
        print("Check the do_transform implementation.")
    
    sys.exit(0 if success else 1)
