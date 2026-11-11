// The only file you edit. Each screen loads index.html?screen=<name>.
// A screen inherits everything in `defaults` and overrides what it lists.
var QUIET_CONFIG = {
  defaults: {
    stateUrl: 'state.json',   // where the three lines come from
    art: ['art/dune.svg', 'art/field.svg', 'art/moon.svg'],
    artMinutes: 30,           // how long each piece stays up
    glanceSeconds: 20,        // how long info stays before returning to art
    whisper: true,            // small clock in the corner during art mode
    apps: []                  // play mode is off when this is empty
  },

  screens: {
    // Example. `tizen` is the app id used on a Frame; `url` is the fallback
    // everywhere else. Replace with real screens once the hardware is known.
    demo: {
      apps: [
        { name: 'YouTube', url: 'https://www.youtube.com/tv' },
        { name: 'Plex', url: 'https://app.plex.tv' }
      ]
    }
  }
};
