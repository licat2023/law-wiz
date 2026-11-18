package com.lawwiz.business.qa;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** Replay one running answer to authorized subscribers without storing drafts in the database. */
final class QaAnswerStream {
    private static final long SUBSCRIPTION_TIMEOUT_MS = 85_000;
    private final StringBuilder draft = new StringBuilder();
    private final List<SseEmitter> subscribers = new ArrayList<>();
    private boolean finished;

    synchronized SseEmitter subscribe() {
        if (finished) {
            return finishedSubscription();
        }
        var emitter = new SseEmitter(SUBSCRIPTION_TIMEOUT_MS);
        emitter.onCompletion(() -> detach(emitter));
        emitter.onTimeout(() -> detach(emitter));
        emitter.onError(error -> detach(emitter));
        if (send(emitter, "delta", Map.of("text", draft.toString()))) {
            subscribers.add(emitter);
        }
        return emitter;
    }

    synchronized void append(String text) {
        draft.append(text);
        var data = Map.of("text", text);
        for (var emitter : List.copyOf(subscribers)) {
            if (!send(emitter, "delta", data)) {
                subscribers.remove(emitter);
            }
        }
    }

    synchronized void finish() {
        finished = true;
        for (var emitter : List.copyOf(subscribers)) {
            finish(emitter);
        }
        subscribers.clear();
    }

    static SseEmitter finishedSubscription() {
        var emitter = new SseEmitter(SUBSCRIPTION_TIMEOUT_MS);
        finish(emitter);
        return emitter;
    }

    private synchronized void detach(SseEmitter emitter) {
        subscribers.remove(emitter);
    }

    private static void finish(SseEmitter emitter) {
        if (send(emitter, "done", Map.of())) {
            emitter.complete();
        }
    }

    private static boolean send(SseEmitter emitter, String event, Map<String, String> data) {
        try {
            emitter.send(SseEmitter.event().name(event).data(data, MediaType.APPLICATION_JSON));
            return true;
        } catch (IOException | IllegalStateException disconnected) {
            return false;
        }
    }
}
