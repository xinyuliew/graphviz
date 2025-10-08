import time
import json
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from utils.docker import ensure_docker_running, start_neo4j_container
from knowledgegraph import KnowledgeGraph
from languagemodel import LocalLLM
from openai import OpenAI
from utils.utils import debug_print
import difflib
from datetime import datetime
import re
import os
from collections import deque

OPENAI_API_KEY = 0
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)  

short_term_memory = deque(maxlen=20)

# initialisation
ensure_docker_running()
start_neo4j_container()
kg = KnowledgeGraph()
import_data = kg.import_csv_once('/Users/trixieliew/Desktop/social_media_kg_project/data/reddit_vaccine_discourse.csv')  # Import data from CSV

llm = LocalLLM()  # Initialize LLM

@app.route('/')
def index():
    return render_template('index.html')
    
# API endpoint with pagination
@app.route('/api/facts', methods=['GET'])
def get_facts():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 100))
    skip = (page - 1) * page_size
    facts = kg.get_facts_batch(skip=skip, limit=page_size)
    return jsonify(facts)

@app.route('/api/add_fact', methods=['POST'])
def add_fact():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body cannot be empty", "refresh": False}), 400
        subject = data.get('subject')
        predicate = data.get('predicate')
        object_ = data.get('object')
        if not all([subject, predicate, object_]):
            return jsonify({"error": "Missing required fields (subject, predicate, object)", "refresh": False}), 400
        success = kg.add_fact(subject, predicate, object_, src="Manual", original_message=None)
        if success:
            return jsonify({"message": f"Fact added: {subject} {predicate} {object_}", "refresh": True}), 200
        else:
            return jsonify({"error": f"Fact already exists: {subject} {predicate} {object_}", "refresh": False}), 409  # Use 409 Conflict status
    except Exception as e:
        debug_print(f"Internal server error in add_fact: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}", "refresh": False}), 500

@app.route('/api/update_fact', methods=['POST'])
def update_fact():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body cannot be empty", "refresh": False}), 400
        subject = data.get('subject')
        old_predicate = data.get('old_predicate')
        old_object = data.get('old_object')
        new_predicate = data.get('new_predicate')
        id = data.get('id')
        if not all([subject, old_predicate, old_object, new_predicate, id]):
            return jsonify({"error": "Missing required fields (subject, old_predicate, old_object, new_predicate, id)", "refresh": False}), 400
        success = kg.update_fact(subject, old_predicate, old_object, new_predicate, new_src="Manual", new_original_message=None)
        if success:
            return jsonify({"message": f"Fact updated: {subject} {old_predicate} {old_object} (ID: {id}) to {subject} {new_predicate} {old_object}", "refresh": True}), 200
        return jsonify({"error": f"Update failed: {subject} {old_predicate} {old_object} (ID: {id}) not found or new predicate is same", "refresh": False}), 404
    except Exception as e:
        debug_print(f"Internal server error in update_fact: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}", "refresh": False}), 500

@app.route('/api/update_timeline', methods=['GET'])
def update_timeline():
    subject = request.args.get('subject')
    object_ = request.args.get('object')
    id = request.args.get('id')
    if not all([subject, object_, id]):
        return jsonify({"error": "Missing required fields (subject, object, id)"}), 400
    timeline = kg.get_update_timeline(subject, object_, id)
    return jsonify(timeline)
    


@app.route('/api/delete_fact', methods=['POST'])
def delete_fact():
    start_time = time.time()

    data = request.get_json()
    subject = data.get('subject')
    predicate = data.get('predicate')
    object_ = data.get('object')

    if not all([subject, predicate, object_]):
        duration = (time.time() - start_time) * 1000  # duration in milliseconds
        print(f"[MONITOR] /api/delete_fact took {duration:.2f}ms (400 Missing fields)")
        return jsonify({"error": "Missing required fields", "refresh": False}), 400

    success = kg.delete_fact(subject, predicate, object_)
    duration = (time.time() - start_time) * 1000

    if success:
        print(f"[MONITOR] /api/delete_fact took {duration:.2f}ms (200 OK)")
        return jsonify({"message": f"Fact deleted: {subject} {predicate} {object_}", "refresh": True})

    print(f"[MONITOR] /api/delete_fact took {duration:.2f}ms (400 Not found)")
    return jsonify({"error": f"Delete failed: {subject} {predicate} {object_} not found", "refresh": False}), 400

@app.route('/api/delete_all_facts', methods=['POST'])
def delete_all_facts():
    try:
        success = kg.delete_all_facts()
        if success:
            return jsonify({"message": "All facts deleted", "refresh": True}), 200
        return jsonify({"error": "Failed to delete all facts", "refresh": False}), 500
    except Exception as e:
        debug_print(f"Internal server error in delete_all_facts: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}", "refresh": False}), 500

@app.route('/api/query_entity', methods=['GET'])
def query_entity():
    entity = request.args.get('entity')
    if not entity:
        return jsonify({"error": "Entity parameter is required"}), 400
    try:
        limit = int(request.args.get('limit', 100))
    except ValueError:
        limit = 100

    facts = kg.query_by_entity(entity)
    facts = facts[:limit]
    return jsonify(facts)

@app.route('/api/query_predicate', methods=['GET'])
def query_predicate():
    predicate = request.args.get('predicate')
    if not predicate:
        return jsonify({"error": "Predicate parameter is required"}), 400
    try:
        limit = int(request.args.get('limit', 100))
    except ValueError:
        limit = 100

    facts = kg.query_by_predicate(predicate)
    facts = facts[:limit]
    return jsonify(facts)

@app.route('/api/query_object', methods=['GET'])
def query_object():
    obj = request.args.get('object')
    if not obj:
        return jsonify({"error": "Object parameter is required"}), 400
    try:
        limit = int(request.args.get('limit', 100))
    except ValueError:
        limit = 100

    facts = kg.query_by_object(obj)
    facts = facts[:limit]
    return jsonify(facts)

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        message = data.get('message')
        if not message:
            return jsonify({"error": "Message cannot be empty", "refresh": False}), 400

        # -----------------------------
        # record intent analysis time
        intent_start = time.perf_counter()
        intent_result = llm.analyze_intent_with_gpt(message)
        intent_end = time.perf_counter()
        debug_print(f"Intent analysis result: {intent_result}")
        debug_print(f"Intent extraction time: {intent_end - intent_start:.6f} seconds")
        # -----------------------------

        operation_message = None
        facts = []
        refresh = False
        memory_text = "No related facts found"

        # -----------------------------
        # fallback: if no intent detected, treat as query
        if not any(intent_result.values()):
            intent_result['query'] = {"keywords": message.split()}

        # -----------------------------
        # handle intent operations of add, update, delete, query
        if intent_result.get("add"):
            # existing add logic
            add_data = intent_result["add"]
            try:
                success = kg.add_fact(
                    subject=add_data["subject"],
                    predicate=add_data["predicate"],
                    obj=add_data["object"],
                    src="Chat",
                    original_message=message
                )
                if success:
                    operation_message = f"Fact added: {add_data['subject']} {add_data['predicate']} {add_data['object']}."
                    refresh = True
                else:
                    operation_message = ""
            except Exception as e:
                debug_print(f"Error adding fact: {str(e)}")
                operation_message = ""

        elif intent_result.get("update"):
            # existing update logic
            update_data = intent_result["update"]
            try:
                if update_data["old_predicate"] == update_data["new_predicate"]:
                    operation_message = f"New predicate {update_data['new_predicate']} is same as old predicate {update_data['old_predicate']}, skipping update."
                else:
                    success = kg.update_fact(
                        subject=update_data["subject"],
                        old_predicate=update_data["old_predicate"],
                        object=update_data["object"],
                        new_predicate=update_data["new_predicate"],
                        new_src="Chat",
                        new_original_message=message
                    )
                    if success:
                        operation_message = f"Fact updated: {update_data['subject']} {update_data['old_predicate']} {update_data['object']} to {update_data['subject']} {update_data['new_predicate']} {update_data['object']}."
                        refresh = True
                    else:
                        add_success = kg.add_fact(
                            subject=update_data["subject"],
                            predicate=update_data["new_predicate"],
                            obj=update_data["object"],
                            src="Chat",
                            original_message=message
                        )
                        if add_success:
                            operation_message = f"Original fact not found for update, added new fact: {update_data['subject']} {update_data['new_predicate']} {update_data['object']}."
                            refresh = True
                        else:
                            operation_message = ""
            except Exception as e:
                debug_print(f"Error updating fact: {str(e)}")
                operation_message = ""

        elif intent_result.get("delete"):
            # existing delete logic
            delete_data = intent_result["delete"]
            try:
                success = kg.delete_fact(
                    subject=delete_data["subject"],
                    predicate=delete_data["predicate"],
                    object=delete_data["object"]
                )
                if success:
                    operation_message = f"Fact deleted: {delete_data['subject']} {delete_data['predicate']} {delete_data['object']}."
                    refresh = True
                else:
                    operation_message = ""
            except Exception as e:
                debug_print(f"Error deleting fact: {str(e)}")
                operation_message = ""

        elif intent_result.get("query"):
            # fetch all facts
            facts = kg.get_all_facts()
            memory_text = "\n".join([
                f"{i+1}. {fact['subject']} {fact['predicate']} {fact['object']} (Created At: {fact['created_at']})\nOriginal Message: {fact['original_message']}"
                for i, fact in enumerate(facts)
            ]) if facts else "No related facts found"

        # -----------------------------
        # prepare recent messages for prompt
        recent_messages_for_prompt = "No recent messages"
        if facts:
            recent_count = min(3, len(short_term_memory))
            similar_messages = list(reversed(short_term_memory))[:recent_count]
            recent_messages_for_prompt = "\n".join([
                f"{i+1}. {entry['message']} (Timestamp: {entry['timestamp']})"
                for i, entry in enumerate(similar_messages)
            ]) if similar_messages else "No relevant recent messages"

        full_prompt = f"""
                        Known facts:
                        {memory_text}

                        Recent messages:
                        {recent_messages_for_prompt}

                        User question:
                        {message}

                        Response(Please answer in English.):
                        """
        debug_print(f"Full prompt sent to LLM: {full_prompt}")

        # -----------------------------
        # generate GPT response
        gpt_start = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant managing a memory system."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            response = response.choices[0].message.content.strip()
        except Exception as e:
            debug_print(f"OpenAI error: {str(e)}")
            return jsonify({"error": f"OpenAI failed: {str(e)}", "refresh": False}), 500
        gpt_end = time.perf_counter()
        debug_print(f"GPT response generation time: {gpt_end - gpt_start:.6f} seconds")

        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
        response = re.sub(r'\n\s*\n', '\n', response).strip()

        if operation_message:
            response = f"{operation_message}\n{response}"

        # -----------------------------
        # add current message to short-term memory
        short_term_memory.append({
            "message": message,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        debug_print(f"Final processed response: {response}")
        return jsonify({
            "response": response,
            "recent_messages": recent_messages_for_prompt,
            "refresh": refresh
        })

    except Exception as e:
        debug_print(f"Internal server error: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}", "refresh": False}), 500


if __name__ == "__main__":
    app.run(debug=True)
        # python -m http.server 8000
    # http://localhost:8000/index.html
