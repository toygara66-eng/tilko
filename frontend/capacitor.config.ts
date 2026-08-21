import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.tilko.app",
  appName: "TILKO",
  webDir: "out",
  android: {
    path: "../android",
  },
  server: {
    androidScheme: "https",
  },
};

export default config;
