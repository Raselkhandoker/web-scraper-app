#!/usr/bin/env python3
"""
Stage 2 - composite the original motion-graphics layer onto each base segment.

Overlays enter with fade + slide easing; a cyan tracking ring drifts across the
build segment; impact flashes hit the card and the goal. Every element is from
our own asset set (cyan/magenta/charcoal), replacing the reference's template.
"""
import os, subprocess, shlex

HERE = os.path.dirname(os.path.abspath(__file__))
SEG = os.path.join(HERE, "segments")
AST = os.path.join(HERE, "assets")

def a(name): return os.path.join(AST, name)

def dur(path):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","csv=p=0",path],capture_output=True,text=True)
    return float(r.stdout.strip())

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1800:]); raise SystemExit("ffmpeg composite failed")

def clip(expr):  # clamp helper string
    return f"clip({expr}\\,0\\,1)"

def composite(seg, overlays, out):
    """overlays: list of dicts:
       {img, sin, sout, din, dout, x, y, dx, dy}  (x,y default '0')
       special color flashes use img=white/red with short fades.
    """
    D = dur(os.path.join(SEG, seg))
    inputs = ["-i", os.path.join(SEG, seg)]
    fc = []
    for ov in overlays:
        inputs += ["-loop","1","-t",f"{D:.3f}","-i", a(ov["img"])]
    prev = "0:v"
    for i, ov in enumerate(overlays, start=1):
        sin  = ov.get("sin", 0.0)
        din  = ov.get("din", 0.35)
        sout = ov.get("sout", D)   # fade-out start
        dout = ov.get("dout", 0.3)
        opacity = ov.get("opacity", 1.0)
        lbl = f"o{i}"
        chain = f"[{i}:v]format=rgba,fade=t=in:st={sin:.3f}:d={din:.3f}:alpha=1"
        if sout < D:
            chain += f",fade=t=out:st={sout:.3f}:d={dout:.3f}:alpha=1"
        if opacity < 1.0:
            chain += f",colorchannelmixer=aa={opacity}"
        chain += f"[{lbl}]"
        fc.append(chain)
        # position (supports slide easing via dx/dy over din)
        dx = ov.get("dx", 0); dy = ov.get("dy", 0)
        if "x" in ov: xexpr = ov["x"]
        elif dx: xexpr = f"({dx})*{clip(f'1-(t-{sin:.3f})/{din:.3f}')}"
        else: xexpr = "0"
        if "y" in ov: yexpr = ov["y"]
        elif dy: yexpr = f"({dy})*{clip(f'1-(t-{sin:.3f})/{din:.3f}')}"
        else: yexpr = "0"
        outlbl = f"t{i}"
        fc.append(f"[{prev}][{lbl}]overlay=x='{xexpr}':y='{yexpr}':format=auto:eval=frame[{outlbl}]")
        prev = outlbl
    filtergraph = ";".join(fc)
    cmd = ["ffmpeg","-y"] + inputs + ["-filter_complex", filtergraph,
           "-map", f"[{prev}]", "-frames:v", str(round(D*30)),
           "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",
           os.path.join(SEG, out)]
    run(cmd)
    print("  composited", out, f"({D:.2f}s)")

SCRIM = {"img":"scrims.png","sin":0.0,"din":0.4}
LOGO  = {"img":"logo.png","sin":0.25,"din":0.4}

if __name__ == "__main__":
    # A - title
    composite("A_hook.mp4", [
        SCRIM, LOGO,
        {"img":"title.png","sin":0.45,"din":0.5,"dy":60},
    ], "A_hook_fx.mp4")

    # B - setup: SET PIECE kicker + RAPHINHA lower third
    composite("B_setup.mp4", [
        SCRIM, LOGO,
        {"img":"kicker.png","sin":0.3,"din":0.35,"dx":-60,"sout":4.9,"dout":0.3},
        {"img":"lower_third.png","sin":0.9,"din":0.4,"dy":70,"sout":4.9,"dout":0.35},
    ], "B_setup_fx.mp4")

    # C - build: score chip + moving tracking ring
    composite("C_build.mp4", [
        SCRIM, LOGO,
        {"img":"score.png","sin":0.3,"din":0.4,"dy":-55},
        {"img":"spotlight.png","sin":0.6,"din":0.4,"sout":4.4,"dout":0.4,
         "x":"W*0.55-260+(W*0.10)*sin((t-0.6)*1.1)","y":"H*0.46-260+(H*0.06)*(t-0.6)/4"},
    ], "C_build_fx.mp4")

    # D - card: red flash + BOOKED
    composite("D_card.mp4", [
        SCRIM, LOGO,
        {"img":"red.png","sin":0.15,"din":0.05,"sout":0.28,"dout":0.28,"opacity":0.55},
        {"img":"booked.png","sin":0.4,"din":0.35,"dy":40},
    ], "D_card_fx.mp4")

    # E - goal: white flash on the strike + GOAL burst
    composite("E_goal.mp4", [
        SCRIM, LOGO,
        {"img":"white.png","sin":2.15,"din":0.04,"sout":2.24,"dout":0.3,"opacity":0.8},
        {"img":"goal.png","sin":2.2,"din":0.3,"dy":50},
    ], "E_goal_fx.mp4")

    # F - end card (self-contained scrim+logo)
    composite("F_end.mp4", [
        {"img":"endcard.png","sin":0.2,"din":0.5},
    ], "F_end_fx.mp4")

    print("OVERLAYS DONE")
