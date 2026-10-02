import type { Metadata } from "next";
import { ChatExperience } from "./chat-experience";

export const metadata: Metadata = {
  title: "Chat with Laplace",
  description: "A calm space to explore ideas and think things through.",
};

export default function ChatPage() {
  return <ChatExperience />;
}
