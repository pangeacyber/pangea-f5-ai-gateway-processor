# Installation

As a prerequisite, we assume you have the F5 AI Gateway running in your kubernetes cluster. 
https://aigateway.clouddocs.f5.com/installation/index.html

## Manual Installation

1. Create a local file, which we will use to make a kubernetes secret
```
{
	"base_url_template": "https://{SERVICE_NAME}.aws.us.pangea.cloud",
	"ai_guard_api_token": "pts_xxx"
}
```
2. Create a kubernetes secret
```
$ kubectl create secret generic pangea-sdk-config --from-file=config.json=config.json
```
3. Build and push the docker image:
```
$ docker buildx build --push --tag registry.example.com/pangea-f5-processor .
```
4. Deploy the processor. Here is an example manifest:
```
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pangea-aidr-processor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: pangea-aidr-processor
  template:
    metadata:
      labels:
        app: pangea-aidr-processor
    spec:
      containers:
        - name: pangea-aidr-processor
          image: registry.example.com/pangea-f5-processor:latest
          imagePullPolicy: Always
          env:
            - name: PANGEA_CONFIG_PATH
              value: /etc/pangea/config.json
          volumeMounts:
            - name: pangea-sdk-config
              mountPath: /etc/pangea
              readOnly: true
          ports:
          - containerPort: 9999
            name: http
            protocol: TCP
      volumes:
        - name: pangea-sdk-config
          secret:
            secretName: pangea-sdk-config
---
apiVersion: v1
kind: Service
metadata:
  name: pangea-aidr
spec:
  selector:
    app: pangea-aidr-processor
  ports:
    - name: http
      port: 80
      protocol: TCP
      targetPort: http
  type: ClusterIP
```
5. Update the F5 AI Gateway config to use this processor:
```
processors:
  - name: pangea-ai-guard
    type: external
    config:
      endpoint: http://pangea-aidr.example-ns.svc.cluster.local
      namespace: guardrails
      version: 1
    params: 
      reject: true
      # It supports both modify and reject
      # modify: true
      request_recipe: pangea_prompt_guard
      response_recipe: pangea_llm_response_guard
```
