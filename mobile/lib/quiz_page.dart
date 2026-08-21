import 'package:flutter/material.dart';

import 'models.dart';
import 'stamp_button.dart';

class QuizPage extends StatefulWidget {
  const QuizPage({super.key, required this.questions});

  final List<QuestionItem> questions;

  @override
  State<QuizPage> createState() => _QuizPageState();
}

class _QuizPageState extends State<QuizPage> {
  int _index = 0;
  final Map<String, String> _answers = {};

  bool get _finished => _index >= widget.questions.length;

  void _restart() {
    setState(() {
      _index = 0;
      _answers.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final total = widget.questions.length;
    if (total == 0) {
      return Scaffold(
        appBar: AppBar(title: const Text('Sorular')),
        body: const Center(child: Text('Soru üretilmedi.')),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Sorular')),
      body: Column(
        children: [
          LinearProgressIndicator(
            value: _finished ? 1 : (_index + 1) / total,
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: _finished ? _score(total) : _question(widget.questions[_index], total),
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: _index == 0 ? null : () => setState(() => _index -= 1),
                      child: const Text('Önceki'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton(
                      onPressed: _finished ? _restart : () => setState(() => _index += 1),
                      child: Text(
                        _finished
                            ? 'Baştan çöz'
                            : (_index == total - 1 ? 'Sonucu gör' : 'Sonraki'),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _question(QuestionItem q, int total) {
    final picked = _answers[q.id];
    final keys = q.options.keys.toList()..sort();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Soru ${_index + 1} / $total'),
            StampButton(label: q.timestampLabel, url: q.videoUrlWithT),
          ],
        ),
        if (q.topic.isNotEmpty || q.difficulty.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Wrap(
              spacing: 6,
              children: [q.topic, q.difficulty]
                  .where((t) => t.isNotEmpty)
                  .map((t) => Chip(
                        label: Text(t, style: const TextStyle(fontSize: 11)),
                        visualDensity: VisualDensity.compact,
                      ))
                  .toList(),
            ),
          ),
        const SizedBox(height: 12),
        Text(
          q.text,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.4),
        ),
        const SizedBox(height: 16),
        ...keys.map((k) {
          final isCorrect = picked != null && k == q.correct;
          final isWrong = picked == k && k != q.correct;
          Color? background;
          if (isCorrect) background = Colors.green.withOpacity(0.2);
          if (isWrong) background = Colors.red.withOpacity(0.2);
          return Card(
            color: background,
            child: ListTile(
              title: Text('$k) ${q.options[k]}'),
              onTap: picked != null ? null : () => setState(() => _answers[q.id] = k),
            ),
          );
        }),
        if (picked != null) ...[
          const Divider(height: 32),
          Text(q.explanation, style: const TextStyle(height: 1.4)),
        ],
      ],
    );
  }

  Widget _score(int total) {
    final correct =
        widget.questions.where((q) => _answers[q.id] == q.correct).length;
    return Column(
      children: [
        const SizedBox(height: 32),
        Text(
          '$correct / $total',
          style: TextStyle(
            fontSize: 40,
            fontWeight: FontWeight.bold,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
        const SizedBox(height: 12),
        const Text(
          'Doğru cevap sayın. Yanlışlarını saniye etiketinden tekrar izleyebilirsin.',
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
