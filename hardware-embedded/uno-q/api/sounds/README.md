# Sons de l'enceinte Bluetooth

- `ok`, `refused`, `hello`, `test`, `siren` : générés par `audio.py` au premier démarrage s'ils manquent.
- `voice-*.wav` : messages parlés, produits sur un Mac (voix française « Thomas ») puis copiés sur la carte :

```bash
say -v Thomas -r 175 -o voice-intrus.aiff "Attention. Intrusion détectée. Vous êtes filmé. L'alarme est déclenchée."
afconvert -f WAVE -d LEI16@44100 -c 1 voice-intrus.aiff voice-intrus.wav
```
