import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";

import type { PhotoResponse } from "./types";

export type RootStackParamList = {
  Capture: undefined;
  Review: {
    photoId: number;
    result: PhotoResponse;
    imageUri: string;
  };
  Library: undefined;
};

export type CaptureNav = NativeStackNavigationProp<
  RootStackParamList,
  "Capture"
>;
export type ReviewNav = NativeStackNavigationProp<
  RootStackParamList,
  "Review"
>;
export type ReviewRoute = RouteProp<RootStackParamList, "Review">;
