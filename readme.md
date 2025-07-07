# Halfmind Flow

**Halfmind Flow** explores how radar sensing can support focus at work by detecting presence and breathing patterns to gently intervene when attention drifts.  
This project is part of my Master’s graduation project in the Integrated Product Design program at TU Delft.

## Overview

Halfmind Flow uses a 60 GHz millimeter-wave radar to sense whether someone is at their desk and monitors subtle breathing patterns. It calculates breathing rate variability (BRV) to infer focus and restlessness. When signs of distraction appear, ambient music and light adjust to help restore flow.

## Key Features

- Real-time presence and breathing detection via radar  
- Rule-based classification of work states using BRV  
- Generative music in Max/MSP to support focus  
- Ambient lighting driven by ESP32 with 7 LEDs to visualize breath depth or provide subtle nudges  
- Debug visualizations in PyQT5

## How It Works

1. Radar captures raw signals of presence and chest movements.  
2. Signal processing (FFT and filtering) extracts breathing features.  
3. A rule-based approach uses BRV to estimate current focus state.  
4. Music and lights adjust in response to support sustained attention.

## Tech Stack

- **Hardware:** Infineon BGT60TR13C radar module, ESP32 LED controller  
- **Software:** Python for signal processing, Max/MSP for music generation, PyQT5 for debugging  
- **Future Work:** Integration with Home Assistant and other ambient devices

## Roadmap

- [ ] Refine BRV detection and link to focus/anxiety states  
- [ ] Improve generative music logic  
- [ ] Expand lighting intervention scenarios  
- [ ] Test in real-world work setups and multi-user contexts

## Acknowledgements

- Radar signal processing inspired by work from Prof. Mohammad Alaee-Kerahroodi ([radarmimo GitHub](https://github.com/radarmimo/Download-Center)) and the Infineon Radar SDK.
- Generative music system references UndulaeMusic ([Patreon](https://www.patreon.com/UndulaeMusic)) and other open-source Max/MSP projects.
- Special thanks to my mentors and peers at TU Delft for their valuable guidance and feedback.

## License

This project is released under the XXX License. See [`LICENSE`](./LICENSE) for details.