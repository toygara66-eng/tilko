import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.tilko.site",
  appName: "TILKO",
  webDir: "out",
  android: {
    path: "../android",
  },
  server: {
    androidScheme: "https",
  },
  plugins: {
    CapacitorHttp: {
      enabled: true,
    },
    LocalNotifications: {
      smallIcon: "ic_launcher",
      iconColor: "#f97316",
    },
  },
};

export default config;
