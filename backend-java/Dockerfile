FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -U -B -ntp package

FROM eclipse-temurin:21-jre-noble
WORKDIR /app
RUN apt-get update && apt-get install --no-install-recommends -y fonts-wqy-zenhei curl \
    && rm -rf /var/lib/apt/lists/*
RUN install -d -o 999 -g 999 /app/.data
COPY --from=build /src/target/business-backend-0.1.0.jar /app/app.jar
USER 999:999
EXPOSE 8000
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=45", "-jar", "/app/app.jar"]
