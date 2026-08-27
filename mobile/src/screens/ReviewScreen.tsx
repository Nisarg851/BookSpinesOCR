import { useNavigation, useRoute } from "@react-navigation/native";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  confirmSpine,
  fetchCatalog,
  filterCatalog,
  type ConfirmAction,
} from "../confirm";
import FullImageModal from "../components/FullImageModal";
import type { ReviewNav, ReviewRoute } from "../navigation";
import type { CatalogBook, DetectedSpine } from "../types";

type SpineUiState =
  | { phase: "auto_kept" }
  | { phase: "needs_action" }
  | { phase: "busy" }
  | { phase: "saved"; label: string }
  | { phase: "discarded" }
  | { phase: "error"; message: string; resume: "auto_kept" | "needs_action" };

function initialState(spine: DetectedSpine): SpineUiState {
  const status = spine.match?.status;
  if (status === "AUTO_ACCEPTED" && spine.match?.catalog_book) {
    return { phase: "auto_kept" };
  }
  if (
    status === "CONFIRMED" ||
    status === "CORRECTED"
  ) {
    return {
      phase: "saved",
      label: status === "CORRECTED" ? "Corrected & saved" : "Saved",
    };
  }
  if (status === "DISCARDED") {
    return { phase: "discarded" };
  }
  return { phase: "needs_action" };
}

function hasSuggestedMatch(spine: DetectedSpine): boolean {
  return Boolean(spine.match?.catalog_book);
}

function confidenceLabel(value: number): string {
  return `${Math.round(value * 100)}% match`;
}

export default function ReviewScreen() {
  const navigation = useNavigation<ReviewNav>();
  const route = useRoute<ReviewRoute>();
  const { result, imageUri } = route.params;
  const spines = result.spines ?? [];

  const [ui, setUi] = useState<Record<number, SpineUiState>>(() => {
    const init: Record<number, SpineUiState> = {};
    for (const spine of spines) {
      init[spine.id] = initialState(spine);
    }
    return init;
  });
  const [finishing, setFinishing] = useState(false);
  const [correctSpineId, setCorrectSpineId] = useState<number | null>(null);
  const [catalog, setCatalog] = useState<CatalogBook[]>([]);
  const [fullImageUri, setFullImageUri] = useState<string | null>(null);
  const inFlight = useRef(new Set<number>());

  useEffect(() => {
    let cancelled = false;
    void fetchCatalog()
      .then((books) => {
        if (!cancelled) setCatalog(books);
      })
      .catch(() => {
        /* manual title/author still works without catalog */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const pendingCount = useMemo(
    () =>
      spines.filter((s) => ui[s.id]?.phase === "needs_action").length,
    [spines, ui]
  );
  const autoKeptCount = useMemo(
    () => spines.filter((s) => ui[s.id]?.phase === "auto_kept").length,
    [spines, ui]
  );
  const decidedCount = spines.length - pendingCount;
  const allReviewed = pendingCount === 0;

  const setSpine = useCallback((id: number, next: SpineUiState) => {
    setUi((prev) => ({ ...prev, [id]: next }));
  }, []);

  const runConfirm = useCallback(
    async (
      spine: DetectedSpine,
      body: ConfirmAction,
      onOk: (label: string) => SpineUiState,
      resume: "auto_kept" | "needs_action"
    ) => {
      if (inFlight.current.has(spine.id)) {
        return;
      }
      inFlight.current.add(spine.id);
      setSpine(spine.id, { phase: "busy" });
      try {
        await confirmSpine(spine.id, body);
        setSpine(spine.id, onOk(body.action));
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Couldn’t save this decision.";
        setSpine(spine.id, { phase: "error", message, resume });
      } finally {
        inFlight.current.delete(spine.id);
      }
    },
    [setSpine]
  );

  const onAccept = useCallback(
    (spine: DetectedSpine) => {
      void runConfirm(
        spine,
        { action: "accept" },
        () => ({ phase: "saved", label: "Added to library" }),
        "needs_action"
      );
    },
    [runConfirm]
  );

  const onDiscard = useCallback(
    (spine: DetectedSpine, resume: "auto_kept" | "needs_action") => {
      void runConfirm(
        spine,
        { action: "discard" },
        () => ({ phase: "discarded" }),
        resume
      );
    },
    [runConfirm]
  );

  const onUndoAuto = useCallback(
    (spine: DetectedSpine) => {
      onDiscard(spine, "auto_kept");
    },
    [onDiscard]
  );

  const onCorrectSubmit = useCallback(
    async (spine: DetectedSpine, body: ConfirmAction) => {
      setCorrectSpineId(null);
      await runConfirm(
        spine,
        body,
        () => ({ phase: "saved", label: "Corrected & saved" }),
        "needs_action"
      );
    },
    [runConfirm]
  );

  const finish = useCallback(async () => {
    if (!allReviewed) {
      Alert.alert(
        "Still need decisions",
        `${pendingCount} spine${pendingCount === 1 ? "" : "s"} still need accept, correct, or discard.`
      );
      return;
    }

    const toAccept = spines.filter((s) => ui[s.id]?.phase === "auto_kept");
    setFinishing(true);
    try {
      for (const spine of toAccept) {
        setSpine(spine.id, { phase: "busy" });
        try {
          await confirmSpine(spine.id, { action: "accept" });
          setSpine(spine.id, {
            phase: "saved",
            label: "Added to library",
          });
        } catch (err) {
          const message =
            err instanceof Error ? err.message : "Failed to save auto-match.";
          setSpine(spine.id, {
            phase: "error",
            message,
            resume: "auto_kept",
          });
          Alert.alert("Couldn’t finish", message);
          return;
        }
      }
      navigation.navigate("Library");
    } finally {
      setFinishing(false);
    }
  }, [
    allReviewed,
    pendingCount,
    spines,
    ui,
    setSpine,
    navigation,
  ]);

  if (spines.length === 0) {
    return (
      <View style={styles.emptyWrap}>
        <Text style={styles.title}>No spines found</Text>
        <Text style={styles.emptyBody}>
          We didn’t detect any book spines in this photo. Try standing closer,
          shooting edge-on, and making sure the titles are lit.
        </Text>
        {imageUri ? (
          <Pressable onPress={() => setFullImageUri(imageUri)}>
            <Image source={{ uri: imageUri }} style={styles.emptyPreview} />
          </Pressable>
        ) : null}
        <Pressable
          style={styles.primaryBtn}
          onPress={() => navigation.navigate("Capture")}
        >
          <Text style={styles.primaryBtnText}>Retake photo</Text>
        </Pressable>
        <FullImageModal
          uri={fullImageUri}
          onClose={() => setFullImageUri(null)}
        />
      </View>
    );
  }

  const correctSpine =
    correctSpineId != null
      ? spines.find((s) => s.id === correctSpineId) ?? null
      : null;

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Review detections</Text>
        <Text style={styles.subtitle}>
          {decidedCount} of {spines.length} decided
          {autoKeptCount > 0
            ? ` · ${autoKeptCount} high-confidence ready to add`
            : ""}
          {pendingCount > 0 ? ` · ${pendingCount} need your call` : ""}
        </Text>
        <Text style={styles.hint}>
          High-confidence matches are queued to add — remove any that are wrong
          before you finish. Everything else needs an explicit accept, correct,
          or discard. Tap a crop to enlarge it.
        </Text>

        {spines.map((spine) => (
          <SpineCard
            key={spine.id}
            spine={spine}
            state={ui[spine.id] ?? { phase: "needs_action" }}
            onAccept={() => onAccept(spine)}
            onDiscard={() => onDiscard(spine, "needs_action")}
            onUndoAuto={() => onUndoAuto(spine)}
            onCorrect={() => setCorrectSpineId(spine.id)}
            onOpenImage={(uri) => setFullImageUri(uri)}
            onRetryError={() => {
              const st = ui[spine.id];
              if (st?.phase === "error") {
                setSpine(spine.id, { phase: st.resume });
              }
            }}
          />
        ))}
      </ScrollView>

      <View style={styles.footer}>
        <Pressable
          style={[
            styles.primaryBtn,
            styles.footerBtn,
            (!allReviewed || finishing) && styles.btnDisabled,
          ]}
          disabled={!allReviewed || finishing}
          onPress={() => void finish()}
        >
          {finishing ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.primaryBtnText}>
              {allReviewed
                ? autoKeptCount > 0
                  ? `Add ${autoKeptCount} & done`
                  : "Done"
                : `Decide ${pendingCount} more`}
            </Text>
          )}
        </Pressable>
      </View>

      {correctSpine ? (
        <CorrectModal
          spine={correctSpine}
          catalog={catalog}
          onClose={() => setCorrectSpineId(null)}
          onSubmit={(body) => void onCorrectSubmit(correctSpine, body)}
        />
      ) : null}

      <FullImageModal
        uri={fullImageUri}
        onClose={() => setFullImageUri(null)}
      />
    </View>
  );
}

function SpineCard({
  spine,
  state,
  onAccept,
  onDiscard,
  onUndoAuto,
  onCorrect,
  onOpenImage,
  onRetryError,
}: {
  spine: DetectedSpine;
  state: SpineUiState;
  onAccept: () => void;
  onDiscard: () => void;
  onUndoAuto: () => void;
  onCorrect: () => void;
  onOpenImage: (uri: string) => void;
  onRetryError: () => void;
}) {
  const suggested = hasSuggestedMatch(spine);
  const catalog = spine.match?.catalog_book;
  const conf = spine.match?.confidence ?? 0;
  const busy = state.phase === "busy";

  return (
    <View style={styles.card}>
      <View style={styles.cardRow}>
        {spine.crop_url ? (
          <Pressable onPress={() => onOpenImage(spine.crop_url!)}>
            <Image source={{ uri: spine.crop_url }} style={styles.crop} />
          </Pressable>
        ) : (
          <View style={[styles.crop, styles.cropPlaceholder]} />
        )}
        <View style={styles.cardBody}>
          <Text style={styles.vlmLabel}>Read from spine</Text>
          {spine.vlm_status === "OK" ? (
            <>
              <Text style={styles.bookTitle}>
                {spine.vlm_title || "Untitled"}
              </Text>
              <Text style={styles.bookAuthor}>
                {spine.vlm_author || "Unknown author"}
              </Text>
            </>
          ) : spine.vlm_status === "UNREADABLE" ? (
            <>
              <Text style={styles.unreadable}>Couldn’t read this spine</Text>
              <Text style={styles.muted}>
                {spine.vlm_note ||
                  "Title reader failed — enter the book manually or discard."}
              </Text>
            </>
          ) : (
            <Text style={styles.muted}>
              {spine.vlm_note || "Spine text not available yet"}
            </Text>
          )}

          {state.phase === "auto_kept" && catalog ? (
            <View style={styles.badgeRow}>
              <Text style={styles.badgeOk}>Will add</Text>
              <Text style={styles.mono}>{confidenceLabel(conf)}</Text>
            </View>
          ) : null}

          {state.phase === "needs_action" && suggested && catalog ? (
            <View style={styles.suggestBox}>
              <Text style={styles.vlmLabel}>Suggested catalog match</Text>
              <Text style={styles.suggestTitle}>{catalog.title}</Text>
              <Text style={styles.bookAuthor}>{catalog.author}</Text>
              <Text style={styles.mono}>{confidenceLabel(conf)}</Text>
            </View>
          ) : null}

          {state.phase === "needs_action" && !suggested ? (
            <Text style={styles.muted}>
              No usable catalog match — enter the book or discard.
            </Text>
          ) : null}

          {state.phase === "saved" ? (
            <Text style={styles.statusOk}>{state.label}</Text>
          ) : null}
          {state.phase === "discarded" ? (
            <Text style={styles.statusDiscard}>Discarded</Text>
          ) : null}
          {state.phase === "error" ? (
            <Text style={styles.statusError}>{state.message}</Text>
          ) : null}
        </View>
      </View>

      {busy ? (
        <View style={styles.actionRow}>
          <ActivityIndicator />
          <Text style={styles.muted}>Saving…</Text>
        </View>
      ) : null}

      {state.phase === "auto_kept" ? (
        <View style={styles.actionRow}>
          <Pressable style={styles.secondaryBtn} onPress={onUndoAuto}>
            <Text style={styles.secondaryBtnText}>Remove</Text>
          </Pressable>
        </View>
      ) : null}

      {state.phase === "needs_action" && suggested ? (
        <View style={styles.actionRow}>
          <Pressable style={styles.primaryBtn} onPress={onAccept}>
            <Text style={styles.primaryBtnText}>Accept</Text>
          </Pressable>
          <Pressable style={styles.secondaryBtn} onPress={onCorrect}>
            <Text style={styles.secondaryBtnText}>Correct</Text>
          </Pressable>
          <Pressable style={styles.ghostBtn} onPress={onDiscard}>
            <Text style={styles.ghostBtnText}>Discard</Text>
          </Pressable>
        </View>
      ) : null}

      {state.phase === "needs_action" && !suggested ? (
        <View style={styles.actionRow}>
          <Pressable style={styles.primaryBtn} onPress={onCorrect}>
            <Text style={styles.primaryBtnText}>Enter book</Text>
          </Pressable>
          <Pressable style={styles.ghostBtn} onPress={onDiscard}>
            <Text style={styles.ghostBtnText}>Discard</Text>
          </Pressable>
        </View>
      ) : null}

      {state.phase === "error" ? (
        <View style={styles.actionRow}>
          <Pressable style={styles.secondaryBtn} onPress={onRetryError}>
            <Text style={styles.secondaryBtnText}>Try again</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

function CorrectModal({
  spine,
  catalog,
  onClose,
  onSubmit,
}: {
  spine: DetectedSpine;
  catalog: CatalogBook[];
  onClose: () => void;
  onSubmit: (body: ConfirmAction) => void;
}) {
  const [title, setTitle] = useState(spine.vlm_title || "");
  const [author, setAuthor] = useState(spine.vlm_author || "");
  const [query, setQuery] = useState(spine.vlm_title || "");
  const hits = useMemo(
    () => filterCatalog(catalog, query || title),
    [catalog, query, title]
  );

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalSheet}>
          <Text style={styles.modalTitle}>Correct / enter book</Text>
          <Text style={styles.muted}>
            Search the catalog or type a title and author manually.
          </Text>

          <TextInput
            style={styles.input}
            placeholder="Search catalog…"
            value={query}
            onChangeText={setQuery}
            autoCapitalize="none"
            autoCorrect={false}
          />

          {hits.length > 0 ? (
            <View style={styles.hits}>
              {hits.map((book) => (
                <Pressable
                  key={book.id}
                  style={styles.hitRow}
                  onPress={() =>
                    onSubmit({ action: "correct", catalog_book_id: book.id })
                  }
                >
                  <Text style={styles.suggestTitle}>{book.title}</Text>
                  <Text style={styles.bookAuthor}>{book.author}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          <Text style={styles.vlmLabel}>Or enter manually</Text>
          <TextInput
            style={styles.input}
            placeholder="Title"
            value={title}
            onChangeText={setTitle}
          />
          <TextInput
            style={styles.input}
            placeholder="Author"
            value={author}
            onChangeText={setAuthor}
          />

          <View style={styles.actionRow}>
            <Pressable
              style={[
                styles.primaryBtn,
                !title.trim() && styles.btnDisabled,
              ]}
              disabled={!title.trim()}
              onPress={() =>
                onSubmit({
                  action: "correct",
                  title: title.trim(),
                  author: author.trim(),
                })
              }
            >
              <Text style={styles.primaryBtnText}>Save</Text>
            </Pressable>
            <Pressable style={styles.ghostBtn} onPress={onClose}>
              <Text style={styles.ghostBtnText}>Cancel</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#fff",
  },
  container: {
    padding: 20,
    paddingBottom: 120,
    gap: 12,
  },
  emptyWrap: {
    flex: 1,
    backgroundColor: "#fff",
    padding: 24,
    justifyContent: "center",
    gap: 12,
  },
  emptyBody: {
    fontSize: 15,
    color: "#444",
    lineHeight: 22,
  },
  emptyPreview: {
    width: "100%",
    height: 180,
    resizeMode: "contain",
    backgroundColor: "#f3f3f3",
    borderRadius: 8,
  },
  title: {
    fontSize: 24,
    fontWeight: "600",
  },
  subtitle: {
    fontSize: 14,
    color: "#333",
    fontWeight: "500",
  },
  hint: {
    color: "#555",
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 4,
  },
  card: {
    borderWidth: 1,
    borderColor: "#e4e4e4",
    borderRadius: 10,
    padding: 12,
    gap: 10,
    backgroundColor: "#fafafa",
  },
  cardRow: {
    flexDirection: "row",
    gap: 12,
  },
  crop: {
    width: 56,
    height: 100,
    borderRadius: 4,
    backgroundColor: "#eee",
  },
  cropPlaceholder: {
    borderWidth: 1,
    borderColor: "#ccc",
  },
  cardBody: {
    flex: 1,
    gap: 2,
  },
  vlmLabel: {
    fontSize: 11,
    color: "#666",
    textTransform: "uppercase",
    marginBottom: 2,
  },
  bookTitle: {
    fontSize: 16,
    fontWeight: "600",
    color: "#111",
  },
  bookAuthor: {
    fontSize: 14,
    color: "#444",
  },
  unreadable: {
    fontSize: 15,
    color: "#a33",
    fontWeight: "500",
  },
  muted: {
    fontSize: 13,
    color: "#666",
  },
  mono: {
    fontFamily: Platform.select({
      ios: "Menlo",
      android: "monospace",
      default: "monospace",
    }),
    fontSize: 12,
    color: "#555",
  },
  badgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 6,
  },
  badgeOk: {
    backgroundColor: "#e5f6ec",
    color: "#146c3a",
    overflow: "hidden",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
    fontSize: 12,
    fontWeight: "600",
  },
  suggestBox: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#ddd",
    gap: 2,
  },
  suggestTitle: {
    fontSize: 15,
    fontWeight: "600",
  },
  statusOk: {
    marginTop: 6,
    color: "#146c3a",
    fontWeight: "600",
  },
  statusDiscard: {
    marginTop: 6,
    color: "#666",
    fontWeight: "600",
  },
  statusError: {
    marginTop: 6,
    color: "#a33",
  },
  actionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    alignItems: "center",
  },
  primaryBtn: {
    backgroundColor: "#111",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 40,
  },
  primaryBtnText: {
    color: "#fff",
    fontWeight: "600",
  },
  secondaryBtn: {
    borderWidth: 1,
    borderColor: "#111",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
  },
  secondaryBtnText: {
    color: "#111",
    fontWeight: "600",
  },
  ghostBtn: {
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  ghostBtnText: {
    color: "#666",
    fontWeight: "600",
  },
  btnDisabled: {
    opacity: 0.45,
  },
  footer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: 16,
    paddingBottom: Platform.select({ ios: 28, default: 16 }),
    backgroundColor: "#fff",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#ddd",
  },
  footerBtn: {
    width: "100%",
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  modalSheet: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 20,
    gap: 10,
    maxHeight: "90%",
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: "600",
  },
  input: {
    borderWidth: 1,
    borderColor: "#ccc",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  hits: {
    maxHeight: 160,
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 8,
  },
  hitRow: {
    padding: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#eee",
  },
});
