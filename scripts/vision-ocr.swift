// Optional macOS Vision driver. Local image only; no model download or network.
import Foundation
import Vision
import ImageIO
let args = CommandLine.arguments
if args.count != 2 { fputs("Expected one image path\n", stderr); exit(2) }
let url = URL(fileURLWithPath: args[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false // Engineering values must not be autocorrected.
request.recognitionLanguages = ["en-US"]
do {
  try VNImageRequestHandler(url: url, options: [:]).perform([request])
  let rows: [[String: Any]] = (request.results ?? []).compactMap { observation in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let b = observation.boundingBox
    return ["text": candidate.string, "confidence": candidate.confidence,
            "box": [b.origin.x, b.origin.y, b.size.width, b.size.height]]
  }
  let bytes = try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys])
  FileHandle.standardOutput.write(bytes)
} catch { fputs("Local Vision recognition failed: \(error)\n", stderr); exit(1) }
