import { Image, Modal, Pressable, StyleSheet, Text, View } from "react-native";

type Props = {
  uri: string | null;
  onClose: () => void;
};

/** Full-screen image lightbox — tap anywhere to dismiss. */
export default function FullImageModal({ uri, onClose }: Props) {
  return (
    <Modal
      visible={uri != null}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose}>
        <View style={styles.frame} pointerEvents="box-none">
          {uri ? (
            <Image
              source={{ uri }}
              style={styles.image}
              resizeMode="contain"
            />
          ) : null}
          <Text style={styles.hint}>Tap to close</Text>
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.92)",
    justifyContent: "center",
    alignItems: "center",
    padding: 16,
  },
  frame: {
    width: "100%",
    height: "100%",
    justifyContent: "center",
    alignItems: "center",
  },
  image: {
    width: "100%",
    height: "85%",
  },
  hint: {
    position: "absolute",
    bottom: 36,
    color: "#ccc",
    fontSize: 14,
  },
});
