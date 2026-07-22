#!/usr/bin/env python3
"""
Stage 3 - final assembly.
  * chain segments with varied xfade transitions (correct running offsets)
  * draw a growing cyan progress bar across the whole timeline
  * synthesize an original royalty-free audio bed (pad + pumping bass + kick +
    hats), with whoosh SFX on every cut and a riser+impact on the goal
  * loudness-normalise to -14 LUFS with a limiter (fixes the source's 0 dB clip)
  * export H.264/AAC 1080x1920 30fps, faststart for web
"""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SEG = os.path.join(HERE, "segments")
FPS = 30

SEGMENTS = [
    ("A_hook_fx.mp4",  "fade",       0.5),
    ("B_setup_fx.mp4", "smoothleft", 0.4),
    ("C_build_fx.mp4", "wipeleft",   0.35),
    ("D_card_fx.mp4",  "smoothup",   0.4),
    ("E_goal_fx.mp4",  "fadewhite",  0.4),
    ("F_end_fx.mp4",   None,         0.0),
]

def dur(p):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","csv=p=0",p],capture_output=True,text=True)
    return float(r.stdout.strip())

def run(cmd, label):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2200:]); raise SystemExit(f"failed: {label}")
    return r

def timeline():
    files = [os.path.join(SEG,f) for f,_,_ in SEGMENTS]
    durs = [dur(f) for f in files]
    tds  = [s[2] for s in SEGMENTS]
    # start time of each segment on the FINAL timeline
    starts = [0.0]
    for i in range(1,len(durs)):
        starts.append(starts[i-1] + durs[i-1] - tds[i-1])
    total = starts[-1] + durs[-1]
    # transition centre times (for whoosh sfx)
    cut_times = [starts[i]+durs[i]-tds[i] + tds[i]/2 for i in range(len(durs)-1)]
    return files, durs, tds, starts, total, cut_times

def build_video(files, durs, tds, total):
    inputs = []
    for f in files: inputs += ["-i", f]
    fc = []; prev = "0:v"; off = 0.0
    for i in range(len(SEGMENTS)-1):
        off += durs[i] - tds[i]           # start-of-overlap for i-th transition
        out = f"x{i}"
        fc.append(f"[{prev}][{i+1}:v]xfade=transition={SEGMENTS[i][1]}:"
                  f"duration={tds[i]}:offset={off:.3f}[{out}]")
        prev = out
    fc.append(f"[{prev}]drawbox=x=0:y=0:w='iw*min(t/{total:.3f}\\,1)':h=8:"
              f"color=0x12E7FF@0.95:t=fill[vout]")
    out = os.path.join(HERE,"video_only.mp4")
    run(["ffmpeg","-y"]+inputs+["-filter_complex",";".join(fc),"-map","[vout]",
        "-r",str(FPS),"-c:v","libx264","-preset","slow","-crf","19",
        "-pix_fmt","yuv420p","-movflags","+faststart",out],"xfade")
    print(f"  video_only.mp4 total={total:.2f}s")
    return out

def build_audio(total, goal_t, cut_times):
    """Synthesize an original bed with ffmpeg aevalsrc expressions."""
    T = total
    sr = 48000
    # musical pieces (A-minor feel). All expressions in seconds variable t.
    # 1) evolving pad (Am triad) with slow swell
    pad = ("aevalsrc='"
           "(0.12*sin(2*PI*220*t)+0.10*sin(2*PI*277.18*t)+0.09*sin(2*PI*329.63*t))"
           "*(0.6+0.4*sin(2*PI*t/6))"
           f"':s={sr}:d={T:.3f}[pad]")
    # 2) pumping sub bass (A1/A2) with 120bpm sidechain-style duck
    bass = ("aevalsrc='"
            "0.5*sin(2*PI*110*t)*(0.35+0.65*abs(sin(2*PI*t*2)))"
            f"':s={sr}:d={T:.3f}[bass]")
    # 3) four-on-the-floor kick (pitch-drop sine, every 0.5s)
    kick = ("aevalsrc='"
            "0.9*sin(2*PI*(45+55*exp(-mod(t\\,0.5)*26))*t)*exp(-mod(t\\,0.5)*8.5)"
            f"':s={sr}:d={T:.3f}[kick]")
    # 4) offbeat hats (filtered noise burst)
    hat = ("aevalsrc='"
           "0.18*(random(0)*2-1)*exp(-mod(t-0.25\\,0.5)*55)"
           f"':s={sr}:d={T:.3f}[hatraw]")
    # 5) riser into the goal (1.6s sweep) + boom impact at goal
    r0 = max(goal_t-1.6, 0)
    riser = ("aevalsrc='"
             f"0.0+if(between(t\\,{r0:.3f}\\,{goal_t:.3f}),"
             f"0.33*(random(0)*2-1)*((t-{r0:.3f})/1.6),0)"
             f"':s={sr}:d={T:.3f}[riserraw]")
    boom = ("aevalsrc='"
            f"if(between(t\\,{goal_t:.3f}\\,{goal_t+1.2:.3f}),"
            f"0.85*sin(2*PI*(40+50*exp(-(t-{goal_t:.3f})*7))*t)*exp(-(t-{goal_t:.3f})*3.2),0)"
            f"':s={sr}:d={T:.3f}[boom]")
    # 6) whoosh sfx at each cut (short noise sweep, +/-0.18s around cut)
    wh_terms = []
    for ct in cut_times:
        wh_terms.append(f"if(between(t\\,{ct-0.2:.3f}\\,{ct+0.15:.3f}),"
                        f"0.4*(random(0)*2-1)*exp(-abs(t-{ct:.3f})*10),0)")
    whoosh = ("aevalsrc='" + "+".join(wh_terms) + f"':s={sr}:d={T:.3f}[whraw]")

    fc = [pad, bass, kick, hat, riser, boom, whoosh,
          "[hatraw]highpass=f=6000,volume=0.7[hat]",
          "[riserraw]highpass=f=1200,volume=1.0[riser]",
          "[whraw]bandpass=f=2500:width_type=h:w=3000,volume=1.0[wh]",
          # mix, gentle bus glue, then loudness normalise + limiter
          "[pad][bass][kick][hat][riser][boom][wh]amix=inputs=7:normalize=0:duration=longest[mixed]",
          "[mixed]highpass=f=28,lowpass=f=16000,"
          "acompressor=threshold=-16dB:ratio=3:attack=8:release=180,"
          "loudnorm=I=-14:TP=-1.2:LRA=11,"
          "alimiter=limit=0.95,afade=t=in:st=0:d=0.4,"
          f"afade=t=out:st={T-0.6:.3f}:d=0.6[aout]"]
    out = os.path.join(HERE,"audio.m4a")
    run(["ffmpeg","-y","-filter_complex",";".join(fc),"-map","[aout]",
        "-t",f"{T:.3f}","-ar","48000","-ac","2","-c:a","aac","-b:a","192k",out],"audio")
    print(f"  audio.m4a total={T:.2f}s  goal@{goal_t:.2f}s")
    return out

def mux(video, audio, total):
    out = os.path.join(HERE,"FINAL_raphinha_reel.mp4")
    run(["ffmpeg","-y","-i",video,"-i",audio,"-map","0:v:0","-map","1:a:0",
        "-c:v","copy","-c:a","aac","-b:a","192k","-shortest",
        "-movflags","+faststart",out],"mux")
    print("  ->", out)
    return out

if __name__ == "__main__":
    files, durs, tds, starts, total, cut_times = timeline()
    goal_t = starts[4] + 2.2      # GOAL flash inside segment E (E-local 2.2s)
    print("segment starts:", [round(s,2) for s in starts], "total", round(total,2))
    v = build_video(files, durs, tds, total)
    a = build_audio(total, goal_t, cut_times)
    mux(v, a, total)
    print("FINAL DONE")
