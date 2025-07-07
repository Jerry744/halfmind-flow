# Halfmind Flow

**Halfmind Flow** is an experimental project exploring how radar sensing can be used to detect and support focus during work. By analyzing subtle human presence, breathing patterns, and micro-movements, Halfmind Flow aims to help individuals become more aware of their work states and build healthier, more sustainable focus habits.  
This project is part of my Master’s graduation work for the Integrated Product Design program at TU Delft.

## What is Halfmind Flow?

Halfmind Flow combines non-intrusive radar sensing with signal processing and ambient feedback mechanisms such as generative music and light. It monitors:

- **Presence**: Detects whether someone is at their desk.
- **Breathing Patterns**: Uses millimeter-wave radar to detect micro chest movements.
- **Focus States**: Analyzes breathing stability and posture to estimate if the person is focused, restless, or absent.

When signs of distraction or restlessness are detected, the system provides a gentle intervention by adjusting music and light conditions to help the user regain flow.

## Features

- Real-time radar-based presence and breathing detection  
- Signal processing to classify work states based on breathing patterns and posture  
- Generative music system to support focus  
- Ambient lighting integration for subtle interventions  
- Modular setup for experimenting with different feedback modes

## Tech Stack

- **Hardware:** 60 GHz FMCW millimeter-wave radar (Infineon BGT60TR13C)
- **Software:** Python for radar signal processing and state classification
- **Generative Music:** Max/MSP for live music generation
- **Visualization:** PyQT5 for data visualization. This is for debugging only
- **Future works** Integration with Home Assistant or other smart home systems.

## How it Works

The core flow is:
1. Raw radar signals are streamed and pre-processed.
2. FFT and other signal analysis techniques extract presence and breathing features.
3. A rule-based or simple machine learning classifier determines the user’s current focus state.
4. Based on the state, the system adjusts music and lighting to encourage a return to flow.

## Roadmap

- [ ] Collect more training data to improve breathing pattern classification  
- [ ] Refine generative music rules to better respond to user states  
- [ ] Test multi-user scenarios and different desk setups  
- [ ] Conduct user studies in real work environments  

## Contributing

Contributions are welcome. If you have experience with radar sensing, generative music, or human-centered interventions, feel free to open an issue or submit a pull request.

## Acknowledgements

This project builds upon and would not be possible without the following:

- Radar signal processing techniques inspired by professor Mohammad Alaee-Kerahroodi (https://github.com/radarmimo/Download-Center) and the Infineon Radar SDK.
- The Max/MSP generative music patch by UndulaeMusic (https://www.patreon.com/UndulaeMusic) and adapts ideas from various open-source generative music projects and tutorials.
- Thanks to my graduation mentors and colleagues at TU Delft for their feedback and support throughout the design and development process.

## License

This project is released under the XXX License. See [`LICENSE`](./LICENSE) for details.