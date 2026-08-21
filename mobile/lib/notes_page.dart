import 'package:flutter/material.dart';

import 'models.dart';
import 'stamp_button.dart';

class NotesPage extends StatelessWidget {
  const NotesPage({super.key, required this.notes});

  final List<NoteItem> notes;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Çalışma notları (${notes.length})')),
      body: notes.isEmpty
          ? const Center(child: Text('Not üretilmedi.'))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: notes.length,
              itemBuilder: (context, i) => _NoteCard(note: notes[i]),
            ),
    );
  }
}

class _NoteCard extends StatelessWidget {
  const _NoteCard({required this.note});

  final NoteItem note;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                StampButton(label: note.timestampLabel, url: note.videoUrlWithT),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    note.title.isEmpty ? 'Not' : note.title,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(note.text, style: const TextStyle(height: 1.55)),
            if (note.keyPoints.isNotEmpty) ...[
              const SizedBox(height: 10),
              ...note.keyPoints.map(
                (p) => Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('•  '),
                      Expanded(child: Text(p, style: const TextStyle(height: 1.45))),
                    ],
                  ),
                ),
              ),
            ],
            if (note.mnemonic.isNotEmpty)
              _InfoBox(
                label: 'HAFIZA TEKNİĞİ',
                text: note.mnemonic,
                color: Colors.green,
              ),
            if (note.examTip.isNotEmpty)
              _InfoBox(
                label: 'ÖSYM TUZAĞI',
                text: note.examTip,
                color: Theme.of(context).colorScheme.primary,
              ),
          ],
        ),
      ),
    );
  }
}

class _InfoBox extends StatelessWidget {
  const _InfoBox({required this.label, required this.text, required this.color});

  final String label;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        border: Border(left: BorderSide(color: color, width: 3)),
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(8),
          bottomRight: Radius.circular(8),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 4),
          Text(text, style: const TextStyle(height: 1.45, fontSize: 13)),
        ],
      ),
    );
  }
}
