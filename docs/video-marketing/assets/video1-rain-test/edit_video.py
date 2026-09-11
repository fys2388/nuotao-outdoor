"""
Nuotao Outdoor - Video 1: Tent Rainstorm Test
Auto-editing script using moviepy
"""
import os
from moviepy import (
    ImageClip, AudioFileClip, CompositeVideoClip,
    concatenate_videoclips, TextClip
)

# Paths
BASE_DIR = r"E:\AI\nuotao-ai-os\docs\video-marketing\assets\video1-rain-test"
OUTPUT_PATH = os.path.join(BASE_DIR, "nuotao-tent-rain-test.mp4")

# Video settings
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Image segments: (image_filename, duration_seconds, zoom_direction)
# zoom_direction: "in" = zoom in, "out" = zoom out, "left" = pan left, "right" = pan right
segments = [
    ("01-rainstorm-tent.jpg", 3.0, "in"),      # 0-3s: Hook - rainstorm tent
    ("03-leaking-tent.jpg", 2.5, "in"),         # 3-5.5s: Problem - leaking tent
    ("01-rainstorm-tent.jpg", 2.5, "out"),      # 5.5-8s: Problem cont - Nuotao tent stable
    ("01-rainstorm-tent.jpg", 4.0, "in"),       # 8-12s: Solution - waterproof close-up
    ("02-tent-interior-dry.jpg", 3.0, "in"),    # 12-15s: Solution - dry interior
    ("04-morning-after-storm.jpg", 5.0, "out"), # 15-20s: Solution - morning after
    ("04-morning-after-storm.jpg", 5.0, "in"),  # 20-25s: Social proof - stable scene
    ("01-rainstorm-tent.jpg", 5.0, "out"),      # 25-30s: CTA - product showcase
]

def create_zoomed_clip(img_path, duration, zoom="in", width=WIDTH, height=HEIGHT):
    """Create an ImageClip with Ken Burns zoom effect."""
    clip = ImageClip(img_path)
    
    # Resize to cover the frame (maintain aspect ratio)
    clip = clip.resized(height=height)
    if clip.w < width:
        clip = clip.resized(width=width)
    
    # Center crop to exact dimensions
    x_center = clip.w / 2
    y_center = clip.h / 2
    clip = clip.cropped(x1=x_center - width/2, y1=y_center - height/2,
                         x2=x_center + width/2, y2=y_center + height/2)
    
    # Apply zoom effect
    if zoom == "in":
        # Start at 1.0, end at 1.15
        def zoom_in(t):
            return 1.0 + 0.15 * (t / duration)
        clip = clip.resized(zoom_in)
    elif zoom == "out":
        # Start at 1.15, end at 1.0
        def zoom_out(t):
            return 1.15 - 0.15 * (t / duration)
        clip = clip.resized(zoom_out)
    
    # Re-center after zoom
    clip = clip.with_duration(duration)
    return clip

def make_text_clip(text, duration, start_time, y_pos=0.75, fontsize=42, color="white"):
    """Create a text overlay clip."""
    font_path = r"C:\Windows\Fonts\arialbd.ttf"
    txt = TextClip(
        text=text,
        font_size=fontsize,
        color=color,
        font=font_path,
        method="caption",
        size=(WIDTH - 100, None),
        text_align="center",
    )
    txt = txt.with_position(("center", y_pos * HEIGHT))
    txt = txt.with_start(start_time).with_duration(duration)
    return txt

def main():
    print("Creating video segments...")
    clips = []
    
    for img_file, duration, zoom in segments:
        img_path = os.path.join(BASE_DIR, img_file)
        if not os.path.exists(img_path):
            print(f"WARNING: Image not found: {img_path}")
            continue
        clip = create_zoomed_clip(img_path, duration, zoom)
        clips.append(clip)
        print(f"  Added: {img_file} ({duration}s, zoom={zoom})")
    
    # Concatenate all video clips
    print("Concatenating clips...")
    video = concatenate_videoclips(clips, method="compose")
    
    # Add voiceover audio
    voiceover_path = os.path.join(BASE_DIR, "voiceover.wav")
    if os.path.exists(voiceover_path):
        print("Adding voiceover...")
        voiceover = AudioFileClip(voiceover_path)
        # Trim or pad voiceover to match video duration
        if voiceover.duration > video.duration:
            voiceover = voiceover.subclipped(0, video.duration)
        video = video.with_audio(voiceover)
    else:
        print(f"WARNING: Voiceover not found: {voiceover_path}")
    
    # Add text overlays (captions)
    print("Adding text overlays...")
    text_overlays = [
        # (text, duration, start_time, y_position)
        ("It started pouring...", 2.5, 0.0, 0.72),
        ("This is what happened to my $80 tent", 2.5, 0.5, 0.78),
        ("Most cheap tents leak after 10 min", 2.5, 3.0, 0.75),
        ("You wake up soaking wet", 2.0, 5.5, 0.75),
        ("But THIS Nuotao tent?", 2.0, 7.5, 0.72),
        ("3000mm Waterproof Rating", 2.0, 9.5, 0.75),
        ("Set up in 60 seconds", 2.0, 11.5, 0.78),
        ("Weighs just 4.5 lbs", 2.0, 13.5, 0.75),
        ("Survived the storm ALL NIGHT", 2.5, 15.5, 0.72),
        ("Bone dry inside", 2.0, 18.0, 0.78),
        ("500+ Five-Star Reviews", 2.5, 20.0, 0.72),
        ("Best budget tent of 2026", 2.5, 22.5, 0.78),
        ("Link in bio to grab yours!", 3.0, 25.5, 0.70),
        ("nuotaooutdoor.com", 2.5, 27.0, 0.80),
    ]
    
    text_clips = []
    for text, duration, start, y_pos in text_overlays:
        txt = make_text_clip(text, duration, start, y_pos)
        text_clips.append(txt)
    
    # Add semi-transparent background bar for text readability
    # (skipped for simplicity - text has good contrast on most scenes)
    
    # Composite video with text overlays
    final = CompositeVideoClip([video] + text_clips, size=(WIDTH, HEIGHT))
    
    # Export
    print(f"Exporting video to: {OUTPUT_PATH}")
    final.write_videofile(
        OUTPUT_PATH,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="5000k",
        preset="medium",
        threads=4,
    )
    
    print("Video creation complete!")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Duration: {final.duration:.1f}s")
    print(f"Resolution: {WIDTH}x{HEIGHT}")

if __name__ == "__main__":
    main()
