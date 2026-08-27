import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";

import type { RootStackParamList } from "./src/navigation";
import CaptureScreen from "./src/screens/CaptureScreen";
import ReviewScreen from "./src/screens/ReviewScreen";

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="auto" />
      <Stack.Navigator initialRouteName="Capture">
        <Stack.Screen
          name="Capture"
          component={CaptureScreen}
          options={{ title: "Shelfie" }}
        />
        <Stack.Screen
          name="Review"
          component={ReviewScreen}
          options={{ title: "Review", headerBackTitle: "Capture" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
