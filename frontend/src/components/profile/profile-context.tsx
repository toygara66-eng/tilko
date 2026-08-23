"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getProgress, type PrizeView, type RecommendedVideo } from "@/lib/api";
import { getUserId } from "@/lib/user";
import { getStoredRole } from "@/lib/auth";
import { foxRank, RANK_ACEMI, RANK_EMOJI } from "@/lib/ranks";

const PROFILE_CACHE_KEY = "tilko_profile_flags";

function readFlags(): { isOnboarded: boolean; isTested: boolean; role: string } {
  if (typeof window === "undefined") {
    return { isOnboarded: false, isTested: false, role: "student" };
  }
  try {
    const raw = window.localStorage.getItem(PROFILE_CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as {
        isOnboarded?: boolean;
        isTested?: boolean;
        role?: string;
      };
      return {
        isOnboarded: Boolean(parsed.isOnboarded),
        isTested: Boolean(parsed.isTested),
        role: parsed.role || getStoredRole() || "student",
      };
    }
  } catch {
    /* ignore */
  }
  return {
    isOnboarded: false,
    isTested: false,
    role: getStoredRole() || "student",
  };
}

function writeFlags(flags: { isOnboarded: boolean; isTested: boolean; role: string }) {
  try {
    window.localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify(flags));
  } catch {
    /* ignore */
  }
}

export type Profile = {
  xp: number;
  title: string;
  titleEmoji: string;
  role: string;
  teacherId: string;
  teacherName: string;
  dashboard: string;
  level: number;
  prize: PrizeView | null;
  aiCreditsLeft: number;
  aiCreditLimit: number;
  isPremium: boolean;
  isInTrial: boolean;
  isAdTier: boolean;
  dailyAdCredits: number;
  dailyAdLimit: number;
  trialDaysLeft: number;
  isTested: boolean;
  checkupDue: boolean;
  weakTopics: string[];
  baselineScore: number;
  analysisSummary: string;
  recommendedVideos: RecommendedVideo[];
  examTarget: string;
  examLabel: string;
  isOnboarded: boolean;
  targetScore: number;
  targetIsSet: boolean;
  currentScore: number;
  progressPct: number;
  daysUntilExam: number;
  examDate: string;
  examDateLabel: string;
  today: string;
  todayLabel: string;
  countdownHeadline: string;
  subscriptionExpiresAt: string | null;
};

const EMPTY: Profile = {
  xp: 0,
  title: RANK_ACEMI,
  titleEmoji: RANK_EMOJI,
  role: "student",
  teacherId: "",
  teacherName: "",
  dashboard: "/",
  level: 1,
  prize: null,
  aiCreditsLeft: 7,
  aiCreditLimit: 7,
  isPremium: false,
  isInTrial: true,
  isAdTier: false,
  dailyAdCredits: 1,
  dailyAdLimit: 1,
  trialDaysLeft: 7,
  isTested: false,
  checkupDue: false,
  weakTopics: [],
  baselineScore: 0,
  analysisSummary: "",
  recommendedVideos: [],
  examTarget: "",
  examLabel: "",
  isOnboarded: false,
  targetScore: 85,
  targetIsSet: false,
  currentScore: 0,
  progressPct: 0,
  daysUntilExam: 0,
  examDate: "",
  examDateLabel: "",
  today: "",
  todayLabel: "",
  countdownHeadline: "",
  subscriptionExpiresAt: null,
};

type ProfileContextValue = {
  profile: Profile;
  ready: boolean;
  refresh: () => Promise<void>;
  apply: (patch: Partial<Profile>) => void;
};

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const cached = readFlags();
  const [profile, setProfile] = useState<Profile>({
    ...EMPTY,
    role: cached.role,
    isOnboarded: cached.isOnboarded,
    isTested: cached.isTested,
  });
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await getProgress(getUserId());
      const next: Profile = {
        xp: data.xp,
        title: data.title || foxRank(data.xp).title,
        titleEmoji: data.title_emoji || foxRank(data.xp).emoji,
        role: data.role || getStoredRole() || "student",
        teacherId: data.teacher_id || "",
        teacherName: data.teacher_name || "",
        dashboard: data.dashboard || "/",
        level: data.level,
        prize: data.prize || null,
        aiCreditsLeft: data.ai_credits_left ?? 7,
        aiCreditLimit: data.ai_credit_limit ?? 7,
        isPremium: Boolean(data.is_premium),
        isInTrial: Boolean(data.is_in_trial_period),
        isAdTier: Boolean(data.is_ad_tier),
        dailyAdCredits: data.daily_ad_credits ?? 1,
        dailyAdLimit: data.daily_ad_limit ?? 1,
        trialDaysLeft: data.trial_days_left ?? 0,
        isTested: Boolean(data.is_tested) || Boolean(readFlags().isTested),
        checkupDue: Boolean(data.checkup_due),
        weakTopics: data.weak_topics || [],
        baselineScore: data.baseline_score ?? 0,
        analysisSummary: data.analysis_summary || "",
        recommendedVideos: data.recommended_videos || [],
        examTarget: data.exam_target || "",
        examLabel: data.exam_label || "",
        isOnboarded: Boolean(data.is_onboarded) || Boolean(readFlags().isOnboarded),
        targetScore: data.target_score ?? 85,
        targetIsSet: Boolean(data.target_is_set),
        currentScore: data.current_score ?? 0,
        progressPct: data.progress_pct ?? 0,
        daysUntilExam: data.days_until_exam ?? 0,
        examDate: data.exam_date || "",
        examDateLabel: data.exam_date_label || "",
        today: data.today || "",
        todayLabel: data.today_label || "",
        countdownHeadline: data.countdown_headline || "",
        subscriptionExpiresAt: data.subscription_expires_at || null,
      };
      setProfile(next);
      writeFlags({
        isOnboarded: next.isOnboarded,
        isTested: next.isTested,
        role: next.role,
      });
    } catch {
      setProfile((prev) => {
        const stored = getStoredRole();
        const role =
          stored === "teacher" || stored === "admin" ? stored : prev.role || stored;
        return { ...prev, role };
      });
    } finally {
      setReady(true);
    }
  }, []);

  const apply = useCallback((patch: Partial<Profile>) => {
    setProfile((prev) => {
      const next = { ...prev, ...patch };
      if (
        patch.isOnboarded !== undefined ||
        patch.isTested !== undefined ||
        patch.role !== undefined
      ) {
        writeFlags({
          isOnboarded: next.isOnboarded,
          isTested: next.isTested,
          role: next.role,
        });
      }
      return next;
    });
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ profile, ready, refresh, apply }),
    [profile, ready, refresh, apply],
  );

  return (
    <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>
  );
}

export function useProfile() {
  const ctx = useContext(ProfileContext);
  if (!ctx) {
    throw new Error("useProfile ProfileProvider içinde kullanılmalı.");
  }
  return ctx;
}
