import 'package:flutter/material.dart';

import 'home_page.dart';

void main() {
  runApp(const KpssApp());
}

class KpssApp extends StatelessWidget {
  const KpssApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'KPSS Video Çalışma',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFD4A017),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const HomePage(),
    );
  }
}
