import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'models.dart';

String defaultApiBase() {
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    return 'http://10.0.2.2:8000';
  }
  return 'http://127.0.0.1:8000';
}

class KpssApi {
  KpssApi({String? baseUrl}) : baseUrl = baseUrl ?? defaultApiBase();

  final String baseUrl;

  Future<AnalyzeResponse> analyze({
    required String videoUrl,
    String? subject,
    int questionCount = 5,
  }) async {
    final body = <String, dynamic>{
      'video_url': videoUrl,
      'question_count': questionCount,
    };
    if (subject != null && subject.trim().isNotEmpty) {
      body['subject'] = subject.trim();
    }

    final response = await http
        .post(
          Uri.parse('$baseUrl/analyze'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(const Duration(minutes: 3));

    final decoded = jsonDecode(response.body);
    if (response.statusCode != 200) {
      throw Exception(decoded['detail'] ?? 'Analiz başarısız');
    }
    return AnalyzeResponse.fromJson(decoded as Map<String, dynamic>);
  }
}
