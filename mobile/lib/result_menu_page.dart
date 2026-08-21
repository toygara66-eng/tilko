import 'package:flutter/material.dart';

import 'models.dart';
import 'notes_page.dart';
import 'quiz_page.dart';

class ResultMenuPage extends StatelessWidget {
  const ResultMenuPage({super.key, required this.result});

  final AnalyzeResponse result;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Analiz hazır')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            (result.subject == null
                    ? 'Analiz tamamlandı'
                    : '${result.subject} — analiz tamamlandı') +
                (result.cached ? ' (önbellekten geldi, kota harcanmadı)' : ''),
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 16),
          _menuTile(
            context,
            icon: Icons.sticky_note_2_outlined,
            title: 'Çalışma notları',
            subtitle: '${result.notes.length} madde',
            page: NotesPage(notes: result.notes),
          ),
          const SizedBox(height: 12),
          _menuTile(
            context,
            icon: Icons.quiz_outlined,
            title: 'Sorular',
            subtitle: '${result.questions.length} soru',
            page: QuizPage(questions: result.questions),
          ),
          const SizedBox(height: 24),
          OutlinedButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Başka video analiz et'),
          ),
        ],
      ),
    );
  }

  Widget _menuTile(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String subtitle,
    required Widget page,
  }) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: Icon(icon, size: 32),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => page),
        ),
      ),
    );
  }
}
