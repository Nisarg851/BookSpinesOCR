import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { Pressable, Text } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import type { RootStackParamList } from "./src/navigation";
import CaptureScreen from "./src/screens/CaptureScreen";
import LibraryScreen from "./src/screens/LibraryScreen";
import ReviewScreen from "./src/screens/ReviewScreen";

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <StatusBar style="auto" />
        <Stack.Navigator initialRouteName="Capture">
          <Stack.Screen
            name="Capture"
            component={CaptureScreen}
            options={{ title: "Book Spines OCR", headerShown: false }}
          />
          <Stack.Screen
            name="Review"
            component={ReviewScreen}
            options={{ title: "Review", headerBackTitle: "Back" }}
          />
          <Stack.Screen
            name="Library"
            component={LibraryScreen}
            options={({ navigation }) => ({
              title: "My library",
              headerRight: () => (
                <Pressable
                  onPress={() => navigation.navigate("Capture")}
                  hitSlop={8}
                  style={{ marginRight: 8, paddingHorizontal: 4 }}
                >
                  <Text style={{ fontWeight: "600", fontSize: 16 }}>Scan</Text>
                </Pressable>
              ),
            })}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
