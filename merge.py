import os
import subprocess
import logging

logger = logging.getLogger(__name__)

def merge_episodes(video_dir: str, output_path: str):
    """
    Merges all .mp4 files in video_dir into a single output_path file.
    video_dir: Directory containing episode_.mp4 files.
    output_path: Path for final merged video.
    """
    try:
        # Get all video files in numeric order
        files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
        if not files:
            logger.error("No .mp4 files found for merge.")
            return False
            
        files.sort() # Sorted alphabetically/numerically like episode_001.mp4
        
        list_file_path = os.path.join(video_dir, "list.txt")
        with open(list_file_path, "w") as f:
            for file in files:
                f.write(f"file '{file}'\n")

        # Attempt 1: Fast Copy Merge with timestamp fixes
        # -fflags +genpts: Generate missing presentation timestamps
        # -avoid_negative_ts make_zero: Fixes issues where videos start with negative TS
        command_copy = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file_path,
            "-fflags", "+genpts",
            "-avoid_negative_ts", "make_zero",
            "-c", "copy",
            output_path
        ]
        
        logger.info(f"🚀 Merging (Fast Copy): {os.path.basename(output_path)}")
        process = subprocess.run(command_copy, capture_output=True, text=True)
        
        if process.returncode == 0:
            logger.info(f"✅ Successfully merged episodes (Fast Copy) into {output_path}")
            return True
            
        # Attempt 2: Fallback to Re-encoding (Slower but 100% stable)
        logger.warning(f"⚠️ Fast Merge failed for {os.path.basename(output_path)}. Retrying with re-encoding (Fallback style)...")
        command_slow = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac",
            output_path
        ]
        
        process_slow = subprocess.run(command_slow, capture_output=True, text=True)
        if process_slow.returncode == 0:
            logger.info(f"✅ Successfully merged episodes (Re-encoding) into {output_path}")
            return True
            
        logger.error(f"❌ Both merge attempts failed. Final error:\n{process_slow.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error during merge: {e}")
        return False
