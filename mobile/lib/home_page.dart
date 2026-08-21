import 'package:flutter/material.dart';

import 'api.dart';
import 'result_menu_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _url = TextEditingController();
  final _subject = TextEditingController();
  final _api = KpssApi();
  int _questionCount = 20;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _subject.dispose();
    super.dispose();
  }

  Future<void> _analyze() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await _api.analyze(
        videoUrl: _url.text.trim(),
        subject: _subject.text,
        questionCount: _questionCount,
      );
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ResultMenuPage(result: data)),
      );
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('KPSS Video Çalışma')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'YouTube ders videosunu bölüm bölüm işler; her kavram için detaylı not, '
            'hafıza tekniği ve ÖSYM tuzağı uyarısı çıkarır, ardından sınav kalitesinde '
            'soru üretir.',
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'YouTube bağlantısı',
              hintText: 'https://www.youtube.com/watch?v=...',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _subject,
            decoration: const InputDecoration(
              labelText: 'Konu (isteğe bağlı)',
              hintText: 'Anayasa, Tarih, Coğrafya...',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<int>(
            initialValue: _questionCount,
            decoration: const InputDecoration(
              labelText: 'Soru sayısı',
              border: OutlineInputBorder(),
            ),
            items: const [10, 20, 30, 40, 60]
                .map((n) => DropdownMenuItem(value: n, child: Text('$n')))
                .toList(),
            onChanged: (v) => setState(() => _questionCount = v ?? 20),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _loading ? null : _analyze,
            child: Text(_loading ? 'Altyazı ve sorular hazırlanıyor...' : 'Analiz et'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 16),
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
          ],
        ],
      ),
    );
  }
}
