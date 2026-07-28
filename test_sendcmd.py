import subprocess
import os

sendcmd_content = """
0.0-1.0 [enter] overlay x 0;
1.0-2.0 [enter] overlay x -500;
2.0-3.0 [enter] overlay x -1000;
"""
with open("test_cmd.txt", "w") as f:
    f.write(sendcmd_content)

# create a 3 second dummy video
subprocess.run("ffmpeg -y -f lavfi -i testsrc=duration=3:size=1920x1080:rate=30 -c:v libx264 test_src.mp4", shell=True)

# apply sendcmd
cmd = "ffmpeg -y -i test_src.mp4 -f lavfi -i color=c=black:s=1080x1080:r=30:d=3 -filter_complex \"[1:v][0:v]sendcmd=f=test_cmd.txt,overlay[out]\" -map \"[out]\" -c:v libx264 test_out.mp4"
subprocess.run(cmd, shell=True)
