import { GoogleGenAI, GenerateContentResponse } from "@google/genai";
// Local types.ts import
import { AttackType as LocalAttackType, AttackAnalysis } from '../types';


// Ensure API_KEY is available in the environment variables
const API_KEY = process.env.API_KEY;

if (!API_KEY) {
  // This message will appear in the console where the app is running.
  // The UI will show a more user-friendly error if the API call fails due to this.
  console.error(
    "CRITICAL ERROR: API_KEY environment variable not set. Gemini API calls will fail."
  );
}

// Initialize GoogleGenAI only if API_KEY is present.
// If it's not, calls to generateContentFromLLM will throw an error caught by the UI.
const ai = API_KEY ? new GoogleGenAI({ apiKey: API_KEY }) : null;

export const generateContentFromLLM = async (
  prompt: string,
  modelName: string,
  systemInstruction?: string
): Promise<string> => {
  if (!ai) {
    throw new Error(
      "Gemini API client not initialized. Is API_KEY missing?"
    );
  }

  try {
    const model = ai.models; 
    const config: Record<string, unknown> = {};
    if (systemInstruction) {
      // Note: The current app embeds instructions in the prompt for attack simulation.
      // This is here for general purpose use if needed differently.
      config.systemInstruction = systemInstruction;
    }
    
    const response: GenerateContentResponse = await model.generateContent({
        model: modelName,
        contents: prompt, // Simplified contents for single string prompt
        ...(Object.keys(config).length > 0 && { config }),
    });
    
    return response.text;

  } catch (error) {
    console.error("Error calling Gemini API for content generation:", error);
    if (error instanceof Error) {
      if (error.message.includes("API key not valid")) {
        throw new Error("Invalid API Key. Please check your environment configuration.");
      }
      throw new Error(`Gemini API Error (Content Generation): ${error.message}`);
    }
    throw new Error("An unknown error occurred while communicating with the Gemini API for content generation.");
  }
};


export const generateAttackAnalysis = async (
  attackType: LocalAttackType,
  modelName: string
): Promise<AttackAnalysis | null> => {
  if (!ai) {
    console.error("Gemini API client not initialized for attack analysis. Is API_KEY missing?");
    return null; // Or throw error, but returning null allows UI to degrade gracefully
  }
  if (attackType === LocalAttackType.NONE) {
    return null;
  }

  const analysisPrompt = `You are a cybersecurity expert specializing in LLM vulnerabilities. Analyze the prompt injection attack type: '${attackType}'.
Provide a concise analysis including:
1. Estimated Success Rate: A qualitative assessment (e.g., Low, Medium-Low, Medium, Medium-High, High, Very High) considering common LLM architectures and defenses.
2. Vulnerability Deep Dive: Explain why this attack is effective (or not), what LLM mechanisms it might exploit, and suggest 2-3 ways this attack could be made more potent or other related vulnerabilities it might expose.

Return ONLY a JSON object with the structure:
{
  "successRate": "<Your estimated success rate>",
  "vulnerabilityAnalysis": "<Your detailed vulnerability deep dive>"
}
Do not include any introductory or concluding text outside this JSON object.`;

  try {
    const response: GenerateContentResponse = await ai.models.generateContent({
      model: modelName,
      contents: analysisPrompt,
      config: {
        responseMimeType: "application/json",
        systemInstruction: "You are a cybersecurity expert specializing in LLM vulnerabilities.",
      },
    });

    let jsonStr = response.text.trim();
    const fenceRegex = /^```(\w*)?\s*\n?(.*?)\n?\s*```$/s;
    const match = jsonStr.match(fenceRegex);
    if (match && match[2]) {
      jsonStr = match[2].trim();
    }

    try {
      const parsedData = JSON.parse(jsonStr);
      if (parsedData.successRate && parsedData.vulnerabilityAnalysis) {
        return parsedData as AttackAnalysis;
      } else {
        console.error("Parsed JSON for attack analysis is missing required fields:", parsedData);
        return null;
      }
    } catch (e) {
      console.error("Failed to parse JSON response for attack analysis:", e, "Raw response:", jsonStr);
      return null;
    }
  } catch (error) {
    console.error(`Error calling Gemini API for attack analysis (${attackType}):`, error);
    // Optionally, rethrow or handle specific API errors if needed
    // if (error instanceof Error && error.message.includes("API key not valid")) {
    //   throw new Error("Invalid API Key for attack analysis.");
    // }
    return null; // Graceful degradation: if analysis fails, don't break the app
  }
};