const SAMPLE_DATA_INDEX_START = 0;
const SAMPLE_DATA_INDEX_END = 6;
const NAL_TYPE_INDICATOR_INDEX = 4;
const NAL_TYPE_MASK = 0x1F;
const DELTA_FRAME_ID = 1;

// Assuming 60fps (1/60 * 1000000)
const MICROSECONDS_PER_FRAME = 16666;

let timestamp = 0;
let chunk;

/**
 * Initializes a VideoDecoder instance with the provided configuration.
 *
 * @returns {VideoDecoder} The initialized VideoDecoder instance.
 */
const initializeDecoder = () => {
    const decoderInit = {
        error: (error) => {
            self.postMessage({message: `Decoder error: ${error.message}`, type: "log"});
        },
        output: (frame) => {
            // Send decoded frame back
            self.postMessage({frame, type: "frame"}, [frame]);
        }
    };

    const decoderConfig = {
        avc: {format: "annexb"},
        codec: "avc1.42E01E",
        optimizeForLatency: true
    };

    // Initialize the VideoDecoder instance
    const decoder = new VideoDecoder(decoderInit);

    // Configure the decoder
    decoder.configure(decoderConfig);

    // Log decoder initialization
    self.postMessage({message: "Decoder initialized", type: "log"});

    return decoder;
};

/**
 * Processes video data by decoding it using the VideoDecoder instance.
 *
 * @param {ArrayBuffer} data - The video data to process.
 */
const processVideoData = (data) => {
    try {
        /**
         * Extracts the first 6 bytes of the data as a Uint8Array.
         */
        const dataView = new Uint8Array(data.slice(
            SAMPLE_DATA_INDEX_START,
            SAMPLE_DATA_INDEX_END
        ));

        // Extract NAL unit type (5 LSBs, 0x1F = 00011111)
        const nalType = dataView[NAL_TYPE_INDICATOR_INDEX] & NAL_TYPE_MASK;
        const decoderType = nalType === DELTA_FRAME_ID ? "delta" : "key";

        /**
         * Creates a new EncodedVideoChunk instance.
         */
        chunk = new EncodedVideoChunk({          
            data,
            timestamp,
            type: decoderType
        });

        // Decode the chunk using the VideoDecoder instance
        self.decoder.decode(chunk);

        // Increment the timestamp
        timestamp += MICROSECONDS_PER_FRAME;
    } catch (error) {
        // Log any errors that occur during processing
        self.postMessage({message: `Error decoding video: ${error.message}`, type: "log"});
    }
};

self.onmessage = (event) => {
    if (event.data.type === "init") {
        self.decoder = initializeDecoder();
    } else if (event.data.type === "videoData") {
        processVideoData(event.data.data);
    }
};
