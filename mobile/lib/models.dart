class NoteItem {
  const NoteItem({
    required this.id,
    required this.title,
    required this.text,
    required this.keyPoints,
    required this.mnemonic,
    required this.examTip,
    required this.timestamp,
    required this.timestampLabel,
    required this.videoUrlWithT,
  });

  final String id;
  final String title;
  final String text;
  final List<String> keyPoints;
  final String mnemonic;
  final String examTip;
  final int timestamp;
  final String timestampLabel;
  final String videoUrlWithT;

  factory NoteItem.fromJson(Map<String, dynamic> json) {
    return NoteItem(
      id: json['id'] as String,
      title: (json['title'] as String?) ?? '',
      text: json['text'] as String,
      keyPoints: ((json['key_points'] as List<dynamic>?) ?? const [])
          .map((e) => e.toString())
          .toList(),
      mnemonic: (json['mnemonic'] as String?) ?? '',
      examTip: (json['exam_tip'] as String?) ?? '',
      timestamp: json['timestamp'] as int,
      timestampLabel: json['timestamp_label'] as String,
      videoUrlWithT: json['video_url_with_t'] as String,
    );
  }
}

class QuestionItem {
  const QuestionItem({
    required this.id,
    required this.text,
    required this.options,
    required this.correct,
    required this.explanation,
    required this.topic,
    required this.difficulty,
    required this.timestamp,
    required this.timestampLabel,
    required this.videoUrlWithT,
  });

  final String id;
  final String text;
  final Map<String, String> options;
  final String correct;
  final String explanation;
  final String topic;
  final String difficulty;
  final int timestamp;
  final String timestampLabel;
  final String videoUrlWithT;

  factory QuestionItem.fromJson(Map<String, dynamic> json) {
    final raw = json['options'] as Map<String, dynamic>? ?? {};
    return QuestionItem(
      id: json['id'] as String,
      text: json['text'] as String,
      options: raw.map((k, v) => MapEntry(k, v.toString())),
      correct: json['correct'] as String,
      explanation: json['explanation'] as String,
      topic: (json['topic'] as String?) ?? '',
      difficulty: (json['difficulty'] as String?) ?? '',
      timestamp: json['timestamp'] as int,
      timestampLabel: json['timestamp_label'] as String,
      videoUrlWithT: json['video_url_with_t'] as String,
    );
  }
}

class AnalyzeResponse {
  const AnalyzeResponse({
    required this.videoId,
    required this.videoUrl,
    required this.notes,
    required this.questions,
    this.subject,
    this.cached = false,
  });

  final String videoId;
  final String videoUrl;
  final String? subject;
  final bool cached;
  final List<NoteItem> notes;
  final List<QuestionItem> questions;

  factory AnalyzeResponse.fromJson(Map<String, dynamic> json) {
    return AnalyzeResponse(
      videoId: json['video_id'] as String,
      videoUrl: json['video_url'] as String,
      subject: json['subject'] as String?,
      cached: (json['cached'] as bool?) ?? false,
      notes: (json['notes'] as List<dynamic>)
          .map((e) => NoteItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      questions: (json['questions'] as List<dynamic>)
          .map((e) => QuestionItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
