package com.lawwiz.business.api;

import java.util.concurrent.RejectedExecutionException;

import jakarta.annotation.PreDestroy;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

/** Bound concurrent document and inference work outside the HTTP request threads. */
@Component
public class BackgroundTasks {
    private final ThreadPoolTaskExecutor executor;

    public BackgroundTasks() {
        executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("lawwiz-task-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(75);
        executor.initialize();
    }

    public void submit(Runnable work, Runnable onRejected) {
        try {
            executor.execute(work);
        } catch (RejectedExecutionException error) {
            onRejected.run();
        }
    }

    @PreDestroy
    void shutdown() {
        executor.shutdown();
    }
}
