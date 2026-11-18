FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp package

FROM eclipse-temurin:21-jre-noble
WORKDIR /app
COPY --from=build /src/target/business-backend-0.1.0.jar /app/app.jar
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=45", "-jar", "/app/app.jar"]
