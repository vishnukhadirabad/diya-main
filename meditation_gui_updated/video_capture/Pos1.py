import sys
import os
from moviepy.editor import VideoFileClip, clips_array, vfx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import project_path

def combine_videos_side_by_side(video1_path, video2_path, output_path, speed_factor=2, desired_height=720):
    """
    Combines two videos side by side with synchronized frame rates and speeds up the combined video.

    Args:
        video1_path (str): Path to the first input video.
        video2_path (str): Path to the second input video.
        output_path (str): Path to save the combined output video.
        speed_factor (float, optional): Factor by which to speed up the video. Defaults to 2.
        desired_height (int, optional): Desired height for both videos. Defaults to 720.
    """
    try:
        # Load the first video
        clip1 = VideoFileClip(video1_path)
        print(f"Loaded Video 1: {video1_path} with FPS: {clip1.fps} and Duration: {clip1.duration}s")

        # Load the second video
        clip2 = VideoFileClip(video2_path)
        print(f"Loaded Video 2: {video2_path} with FPS: {clip2.fps} and Duration: {clip2.duration}s")

        # Determine the common frame rate (use the higher frame rate to maintain quality)
        common_fps = max(clip1.fps, clip2.fps)
        print(f"Common FPS set to: {common_fps}")

        # Set both clips to the common frame rate
        clip1 = clip1.set_fps(common_fps)
        clip2 = clip2.set_fps(common_fps)

        # Trim both clips to the shortest duration to ensure synchronization
        min_duration = min(clip1.duration, clip2.duration)
        clip1 = clip1.subclip(0, min_duration)
        clip2 = clip2.subclip(0, min_duration)
        print(f"Both clips trimmed to minimum duration: {min_duration}s")

        # Resize both clips to have the same height
        clip1 = clip1.resize(height=desired_height)
        clip2 = clip2.resize(height=desired_height)
        print(f"Both clips resized to height: {desired_height}px")

        # Combine clips side by side
        final_clip = clips_array([[clip1, clip2]])
        print("Videos combined side by side.")

        # Speed up the combined video
        final_clip = final_clip.fx(vfx.speedx, factor=speed_factor)
        print(f"Combined video sped up by a factor of {speed_factor}x.")

        # Write the output video
        final_clip.write_videofile(output_path, codec='libx264', fps=common_fps, preset='medium')
        print(f"Combined video saved to: {output_path}")

    except Exception as e:
        print(f"An error occurred: {e}")

def main():
    """
    Main function to handle command-line arguments and initiate video combination.
    """
   
    video1_path = str(project_path('video_capture', 'postureanalysis.mp4'))
    video2_path = str(project_path('video_capture', 'output1_video.avi'))
    output_path = str(project_path('video_capture', 'pos_fin_op.avi'))

    # Optional: Adjust speed_factor and desired_height as needed
    speed_factor = 4  # 2x speed
    desired_height = 360  # 720p height

    combine_videos_side_by_side(video1_path, video2_path, output_path, speed_factor, desired_height)

if __name__ == "__main__":
    main()
