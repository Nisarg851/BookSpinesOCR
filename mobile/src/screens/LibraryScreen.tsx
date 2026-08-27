import { useCallback, useState } from "react";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { fetchLibrary, type LibraryEntry } from "../library";
import type { RootStackParamList } from "../navigation";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

type Nav = NativeStackNavigationProp<RootStackParamList, "Library">;

export default function LibraryScreen() {
  const navigation = useNavigation<Nav>();
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (mode: "initial" | "refresh") => {
    if (mode === "refresh") {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const rows = await fetchLibrary();
      setEntries(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load library");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load("initial");
    }, [load])
  );

  if (loading && entries.length === 0) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
        <Text style={styles.muted}>Loading library…</Text>
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        data={entries}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={
          entries.length === 0 ? styles.emptyList : styles.list
        }
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load("refresh")}
          />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No books yet</Text>
            <Text style={styles.muted}>
              Scan a shelf and confirm matches to build your library.
            </Text>
            <Pressable
              style={styles.button}
              onPress={() => navigation.navigate("Capture")}
            >
              <Text style={styles.buttonText}>Scan a shelf</Text>
            </Pressable>
          </View>
        }
        renderItem={({ item }) => (
          <View style={styles.row}>
            {item.crop_url ? (
              <Image source={{ uri: item.crop_url }} style={styles.thumb} />
            ) : (
              <View style={[styles.thumb, styles.thumbPlaceholder]} />
            )}
            <View style={styles.meta}>
              <Text style={styles.title}>{item.title}</Text>
              <Text style={styles.author}>{item.author || "Unknown author"}</Text>
            </View>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#fff",
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#fff",
  },
  list: {
    padding: 16,
    paddingBottom: 32,
    gap: 4,
  },
  emptyList: {
    flexGrow: 1,
    padding: 24,
    justifyContent: "center",
  },
  empty: {
    gap: 10,
    alignItems: "flex-start",
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: "600",
  },
  row: {
    flexDirection: "row",
    gap: 12,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#ddd",
    alignItems: "center",
  },
  thumb: {
    width: 40,
    height: 64,
    borderRadius: 3,
    backgroundColor: "#eee",
  },
  thumbPlaceholder: {
    borderWidth: 1,
    borderColor: "#ccc",
  },
  meta: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: 16,
    fontWeight: "600",
    color: "#111",
  },
  author: {
    fontSize: 14,
    color: "#444",
  },
  muted: {
    color: "#666",
    fontSize: 14,
    lineHeight: 20,
  },
  error: {
    color: "#a33",
    padding: 12,
    paddingBottom: 0,
  },
  button: {
    marginTop: 8,
    backgroundColor: "#111",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
  },
  buttonText: {
    color: "#fff",
    fontWeight: "600",
  },
});
