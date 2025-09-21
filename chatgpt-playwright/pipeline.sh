PROJECT_NAME=$1

if [ -z "$PROJECT_NAME" ]; then
    echo "Usage: $0 <project_name>"
    exit 1
fi

python3 scripts/get_image_prompts.py ${PROJECT_NAME}

# save dir -> projects/${PROJECT_NAME}/prompts.json
PROJECT=${PROJECT_NAME} npx ts-node generateImageLoop_resilient.ts
