#!/usr/bin/env python3
"""
Stage 1 - render the graded footage base for every story segment.

Each segment is trimmed from the source, speed-adjusted (constant speed or a
two-part speed ramp), pushed/panned with a virtual camera (zoompan), then
run through a cinematic teal-orange grade with denoise, sharpen, grain and
vignette. Output: 1080x1920 / 30fps H.264 base clips in segments/.
"""
import os, subprocess, shlex

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source.mp4")
SEG = os.path.join(HERE, "segments")
os.makedirs(SEG, exist_ok=True)
FPS = 30

# Cinematic grade shared by every clip (deliberately unlike the flat broadcast look)
GRADE = ("hqdn3d=2:1.5:4:4,"
         "eq=contrast=1.14:brightness=-0.015:saturation=1.27:gamma=0.97,"
         "curves=r='0/0.02 0.5/0.5 1/0.98':b='0/0.06 0.5/0.47 1/0.92',"
         "colorbalance=rs=-0.05:bs=0.07:gm=0.03,"
         "unsharp=5:5:1.0:5:5:0.2,"
         "noise=alls=6:allf=t,"
         "vignette=PI/4.2")

def run(cmd):
    print("  $", " ".join(shlex.quote(c) for c in cmd[:6]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:])
        raise SystemExit(f"ffmpeg failed for {cmd[-1]}")

def cam(zoom_from, zoom_to, out_frames, panx="0", pany="0"):
    """zoompan virtual-camera push/pan expression -> 1080x1920."""
    z = f"min({zoom_from}+({zoom_to}-{zoom_from})*on/{max(out_frames-1,1)},{max(zoom_from,zoom_to)})"
    x = f"iw/2-(iw/zoom/2)+({panx})"
    y = f"ih/2-(ih/zoom/2)+({pany})"
    return (f"scale=1620:2880:flags=lanczos,"
            f"zoompan=z='{z}':d=1:x='{x}':y='{y}':s=1080x1920:fps={FPS}")

def base_clip(name, ss, t, out_dur, zf, zt, panx="0", pany="0"):
    """Constant-speed graded segment."""
    out_frames = round(out_dur * FPS)
    factor = out_dur / t
    vf = f"setpts={factor:.5f}*PTS,fps={FPS},{cam(zf,zt,out_frames,panx,pany)},{GRADE}"
    out = os.path.join(SEG, f"{name}.mp4")
    run(["ffmpeg","-y","-ss",f"{ss}","-t",f"{t}","-i",SRC,"-an","-vf",vf,
         "-frames:v",str(out_frames),
         "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",out])
    return out

def ramp_clip(name, parts, zf, zt, panx="0", pany="0"):
    """Two-part speed ramp: parts=[(ss,t,speed_out_dur), ...] concatenated."""
    tmpfiles = []
    total_frames = round(sum(p[2] for p in parts) * FPS)
    # render each part at constant speed WITHOUT camera (camera applied after concat)
    for i,(ss,t,od) in enumerate(parts):
        factor = od / t
        f = round(od*FPS)
        vf = f"setpts={factor:.5f}*PTS,fps={FPS}"
        tf = os.path.join(SEG, f"{name}_p{i}.mp4")
        run(["ffmpeg","-y","-ss",f"{ss}","-t",f"{t}","-i",SRC,"-an","-vf",vf,
             "-frames:v",str(f),"-c:v","libx264","-preset","fast","-crf","16","-pix_fmt","yuv420p",tf])
        tmpfiles.append(tf)
    # concat
    lst = os.path.join(SEG, f"{name}_list.txt")
    with open(lst,"w") as fh:
        for tf in tmpfiles: fh.write(f"file '{tf}'\n")
    joined = os.path.join(SEG, f"{name}_joined.mp4")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",lst,"-c","copy",joined])
    # camera + grade over the joined ramp
    vf = f"fps={FPS},{cam(zf,zt,total_frames,panx,pany)},{GRADE}"
    out = os.path.join(SEG, f"{name}.mp4")
    run(["ffmpeg","-y","-i",joined,"-an","-vf",vf,"-frames:v",str(total_frames),
         "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",out])
    for tf in tmpfiles+[joined,lst]:
        try: os.remove(tf)
        except OSError: pass
    return out

if __name__ == "__main__":
    print("A hook/title (hero portrait, near-freeze slow push-in)")
    base_clip("A_hook", ss=28.95, t=0.75, out_dur=3.2, zf=1.14, zt=1.34)

    print("B setup (corner placement, push-in biased low to drop top callout)")
    base_clip("B_setup", ss=1.0, t=5.4, out_dur=5.4, zf=1.20, zt=1.36, pany="ih*0.16")

    print("C build (build-up play, gentle push-in + left parallax, sped up)")
    base_clip("C_build", ss=6.7, t=5.9, out_dur=5.0, zf=1.12, zt=1.24, panx="-iw*0.06*on/150")

    print("D tension (yellow-card beat, punch-in)")
    base_clip("D_card", ss=16.3, t=3.4, out_dur=3.8, zf=1.12, zt=1.34, pany="ih*0.04")

    print("E payoff (goal, speed RAMP: approach normal -> strike slow-mo)")
    ramp_clip("E_goal", parts=[(24.9,2.1,2.2),(27.0,1.4,2.6)], zf=1.10, zt=1.30)

    print("F endcard (hero portrait, continue push-in)")
    base_clip("F_end", ss=28.95, t=0.7, out_dur=2.8, zf=1.20, zt=1.40)
    print("BASE SEGMENTS DONE")
