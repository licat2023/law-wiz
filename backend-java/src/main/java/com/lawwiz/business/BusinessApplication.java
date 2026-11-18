package com.lawwiz.business;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.WebApplicationType;

/** Starts the Java business API. */
@SpringBootApplication
public class BusinessApplication {
    public static void main(String[] args) {
        if (java.util.Arrays.stream(args).anyMatch(arg -> arg.startsWith("--lawwiz.file-migration="))) {
            try (var context = new SpringApplicationBuilder(BusinessApplication.class)
                    .web(WebApplicationType.NONE).run(args)) {
                return;
            }
        }
        SpringApplication.run(BusinessApplication.class, args);
    }
}
