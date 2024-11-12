import board
import digitalio
import busio
import keypad
import time
import adafruit_midi
from adafruit_midi.control_change import ControlChange
from adafruit_midi.pitch_bend import PitchBend
from adafruit_midi.note_off import NoteOff
from adafruit_midi.note_on import NoteOn


class Sequence:
    def __init__(self, voices, steps):
        # Create a dictionary, with N voices as keys, and list of N steps as values
        self.data = {i: [False for _ in range(steps)] for i in range(voices)}

    def __str__(self):
        # Render readable output
        summary = []
        for voice in self.data.keys():
            summary.append(f"Voice {voice}: {self.data[voice]}")
        return "\n".join(summary)

    def update(self, voice, step, state):
        self.data[voice][step] = state


# Initialize a blank sequence
sequence = Sequence(voices=2, steps=16)


class CD4096:
    def index_mask(i):
        return (i // 8, 1 << (i % 8))

    def __init__(self, clock_pin, strobe_pin, data_pin, number):
        self.byte_array = bytearray(number)
        self.clock_pin = digitalio.DigitalInOut(clock_pin)
        self.clock_pin.direction = digitalio.Direction.OUTPUT
        self.strobe_pin = digitalio.DigitalInOut(strobe_pin)
        self.strobe_pin.direction = digitalio.Direction.OUTPUT
        self.data_pin = digitalio.DigitalInOut(data_pin)
        self.data_pin.direction = digitalio.Direction.OUTPUT

    def __setitem__(self, i, b):
        index, mask = CD4096.index_mask(i)
        if index < len(self.byte_array):
            if b:
                self.byte_array[index] |= mask
            else:
                self.byte_array[index] &= ~mask

    def __getitem__(self, i):
        index, mask = CD4096.index_mask(i)
        if index < len(self.byte_array):
            return self.byte_array[index] & mask != 0
        return False

    def strobe(self):
        self.strobe_pin.value = True
        time.sleep(0.00001)  # I bet we don't need this
        self.strobe_pin.value = False

    def write(self):
        for i in range(8 * len(self.byte_array)):
            self.data_pin.value = self[i]
            self.clock_pin.value = True
            self.clock_pin.value = False
        self.strobe()


# Return duration of 16th note in ns
def bpm_to_ms(bpm):
    return 60000 / bpm / 4 / 1000


# Instantiate CD4096 output shift register for step indicator
leds = CD4096(
    data_pin=board.GP12, clock_pin=board.GP11, strobe_pin=board.GP10, number=2
)

# Instantiate keypad to process switch input
keys = keypad.ShiftRegisterKeys(
    clock=board.GP9,
    data=board.GP8,
    latch=board.GP7,
    key_count=(16,),
    value_when_pressed=False,
    value_to_latch=False,
)

# Run a reset on the keypad object to detect already switched switches
keys.reset()

# Create midi uart device
uart = busio.UART(tx=board.GP16, rx=board.GP17, baudrate=31250, timeout=0.001)

# Create midi object

midi_in_channel = 10
midi_out_channel = 10

midi = adafruit_midi.MIDI(
    # midi_in=uart,
    midi_out=uart,
    # in_channel=(midi_in_channel - 1),
    out_channel=(midi_out_channel - 1),
    # debug=False,
)

beats = 16
step = 0
bpm = 60

# Create a dict mapping between voice number and note
voice_notes = {
    0: "C1",  # Bass drum
    1: "D1",  # Snare
    2: "F#1",  # Closed hat
    3: "Bb1",  # Open hat
}

# Save starting time
last_tick = time.monotonic()

while True:
    # Set current_step to step mod 16
    current_step = step % 16
    # print("on step " + str(step % 16 + 1))
    # Set the step LED to illuminate
    leds[current_step] = True
    # Illuminate the step LED
    leds.write()

    # Send MIDI messages
    # Collect voices
    voices = sequence.data.keys()

    # Iterate through voices
    for voice in voices:
        # Check to see if this step is active
        if sequence.data[voice][current_step]:
            # Send the note corresponding to the current voice
            midi.send(NoteOn(voice_notes[voice]))

    if time.monotonic() >= last_tick + bpm_to_ms(bpm):
        leds[current_step] = False
        step += 1
        last_tick = time.monotonic()

    event = keys.events.get()
    if event:
        print(event)
        if event.pressed:
            # print(f"Key {event.key_number} pressed")
            # Update the sequence (only once voice/row for now)
            sequence.update(voice=0, step=event.key_number, state=True)
        elif event.released:
            # print(f"Key {event.key_number} released")
            sequence.update(voice=0, step=event.key_number, state=False)
        # print(sequence)
