from shutil import copyfile
import os
import random

BASE = 'base.jpg'
os.chdir('/home/pi/Downloads')

for link in range(1, 50):
    for loop in range(0, 5):
        passed = bool(random.getrandbits(1)) or bool(random.getrandbits(1)) or bool(random.getrandbits(1))
        check = "GOOD" if passed else "FAIL"
        copyfile(BASE, f"LEFT_{check}_LP-{loop}_ID-{link}.jpg")
        passed = bool(random.getrandbits(1)) or bool(random.getrandbits(1)) or bool(random.getrandbits(1))
        check = "GOOD" if passed else "FAIL"
        copyfile(BASE, f"RIGHT_{check}_LP-{loop}_ID-{link}.jpg")

