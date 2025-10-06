import ollama
import spacy
import re
from openai import OpenAI
from typing import Dict, Optional

class LocalLLM:
    def __init__(self, model_name="deepseek-r1:7b"):
        self.model_name = model_name
        try:
            self.nlp = spacy.load("en_core_web_sm")  # English model; use "zh_core_web_sm" for Chinese
            debug_print(f"Using local model: {self.model_name} and spaCy model")
        except Exception as e:
            debug_print(f"Failed to load spaCy model: {str(e)}")
            raise Exception("spaCy model loading failed, please ensure the model is installed")

    def chat(self, prompt):
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            return response['message']['content'].strip()
        except Exception as e:
            print(f"LLM call failed: {str(e)}")
            return None
        

    def analyze_intent_with_gpt(self, user_input: str, id: Optional[str] = None) -> Dict:
        """
        Analyze intent using OpenAI GPT and return structured data.
        """
        result = {
            "add": None,
            "update": None,
            "delete": None,
            "query": None
        }

        prompt = f"""
        To implement a better LLM long-term memory management system, analyze the input to determine whether to add, update, delete memory triples, or query information. Extract accurate memory triples (subject, predicate, object), return JSON. For add, update, or delete intents, ensure all fields (subject, predicate, object for add/delete; subject, old_predicate, object, new_predicate for update) are non-empty if the intent is not null. For query, extract multiple keywords from the sentence, such as pronouns (I, he, she, etc.), names, titles (teacher, my Dad), predicates.

        Input: "{user_input}"

        Output:
        {{
            "add": null or {{"subject": str, "predicate": str, "object": str}},
            "update": null or {{"subject": str, "old_predicate": str, "object": str, "new_predicate": str}},
            "delete": null or {{"subject": str, "predicate": str, "object": str}},
            "query": null or {{"keywords": [str]}}
        }}

        Examples:
        Input: "Pizza is my favorite food."
        Output: {{"add": {{"subject": "Pizza", "predicate": "is", "object": "my favorite food"}}, "update": null, "delete": null, "query": null}}

        Input: "Alice is no longer friends with Bob, now she is married to him."
        Output: {{"add": null, "update": {{"subject": "Alice", "old_predicate": "friends with", "object": "Bob", "new_predicate": "married to"}}, "delete": null, "query": null}}

        Input: "Forget that Alice is friends with Bob."
        Output: {{"add": null, "update": null, "delete": {{"subject": "Alice", "predicate": "friends with", "object": "Bob"}}, "query": null}}

        Input: "What is the relationship between Alice and Bob?"
        Output: {{"add": null, "update": null, "delete": null, "query": {{"keywords": ["Alice", "Bob", "relationship"]}}}}
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                response_format={"type": "json_object"}
            )
            result_str = response.choices[0].message.content
            debug_print(f"GPT response: {result_str}")

            # Parse JSON
            parsed = json.loads(result_str)
            if all(key in parsed for key in ["add", "update", "delete", "query"]):
                return parsed
            debug_print("Invalid GPT response format")
            return result
        except Exception as e:
            debug_print(f"OpenAI error: {str(e)}")
            return result

    def classify_intent(self, user_input):
        """Classify user intent: add, update, delete, or query"""
        user_input_lower = user_input.lower()
        doc = self.nlp(user_input)

        # Prioritize question detection (query intent)
        question_words = ["which", "what", "who", "where", "when", "why", "how"]
        if any(user_input_lower.startswith(word) for word in question_words) or user_input_lower.startswith("does"):
            return "query"

        # Keyword detection
        if any(keyword in user_input_lower for keyword in ["forget", "remove", "delete"]):
            return "delete"
        if any(keyword in user_input_lower for keyword in ["no longer", "now", "change to", "instead"]):
            return "update"

        # Syntactic analysis: check subject-predicate structure for add intent
        has_subject = any(token.dep_ == "nsubj" for token in doc)
        has_verb = any(token.pos_ == "VERB" and token.dep_ in ["ROOT", "aux"] and token.tag_ != "VBG" for token in doc)
        has_object = any(token.dep_ in ["dobj", "pobj"] for token in doc)
        if has_subject and has_verb:
            if not any(token.text.lower() in question_words for token in doc):
                return "add"

        return "query"  # Default to query

    def extract_entities_and_predicate(self, user_input):
        """Extract entities and predicate using syntactic analysis"""
        try:
            doc = self.nlp(user_input)
            subject = None
            objects = []
            predicate = None

            # Extract subject (nsubj), predicate (VERB), and object (dobj or pobj)
            for token in doc:
                if token.dep_ == "nsubj" and (token.ent_type_ or token.pos_ in ["NOUN", "PROPN"]):
                    subject = token.text
                elif token.dep_ in ["dobj", "pobj"] and token.pos_ in ["NOUN", "PROPN", "VERB"]:
                    objects.append(token.text)
                elif token.dep_ in ["ROOT", "aux"] and token.pos_ == "VERB" and token.tag_ != "VBG":
                    predicate = token.text

            # Supplement with NER entities
            for ent in doc.ents:
                if ent.text != subject and ent.text not in objects:
                    objects.append(ent.text)

            # Handle complex objects (e.g., "old fashioned life skills")
            for chunk in doc.noun_chunks:
                if chunk.root.dep_ in ["dobj", "pobj"] and chunk.text != subject and chunk.text not in objects:
                    objects.append(chunk.text)

            entities = [subject] + objects if subject else objects

            if len(entities) > 3:
                entities = entities[:3]

            debug_print(f"Extracted subject: {subject}, objects: {objects}, predicate: {predicate}")
            return {
                "subject": subject,
                "objects": objects,
                "predicate": predicate
            }
        except Exception as e:
            debug_print(f"Error in extract_entities_and_predicate: {str(e)}")
            return {"subject": None, "objects": [], "predicate": None}

    def extract_new_predicate(self, user_input):
        """Extract new predicate for update intent"""
        try:
            doc = self.nlp(user_input)
            update_keywords = ["no longer", "now", "change to", "instead"]
            update_found = False
            for token in doc:
                if token.lower_ in update_keywords:
                    update_found = True
                    for subsequent in doc[token.i + 1:]:
                        if subsequent.pos_ == "VERB" and subsequent.tag_ != "VBG":  # Exclude gerunds
                            return subsequent.text
            if update_found:
                match = re.search(r"(no longer|now|change to|instead)\s+(\w+)", user_input.lower())
                if match:
                    return match.group(2)
            return None
        except Exception as e:
            debug_print(f"Error in extract_new_predicate: {str(e)}")
            return None

    def analyze_intent_and_extract(self, user_input, id=None):
        """Analyze intent and extract triples, including query"""
        result = {"add": None, "update": None, "delete": None, "query": None}

        # Classify intent
        intent = self.classify_intent(user_input)
        parsed = self.extract_entities_and_predicate(user_input)
        subject = parsed["subject"]
        objects = parsed["objects"]
        predicate = parsed["predicate"]

        # Populate result based on intent
        if intent == "add" and subject and objects and predicate:
            result["add"] = {
                "subject": subject,
                "predicate": predicate,
                "object": objects[0] if objects else None
            }
        elif intent == "update" and subject and objects and predicate and id:
            new_predicate = self.extract_new_predicate(user_input)
            if new_predicate:
                result["update"] = {
                    "subject": subject,
                    "old_predicate": predicate,
                    "old_object": objects[0] if objects else None,
                    "new_predicate": new_predicate,
                    "id": id  # From frontend
                }
        elif intent == "delete" and subject and objects and predicate and id:
            result["delete"] = {
                "subject": subject,
                "predicate": predicate,
                "object": objects[0] if objects else None,
                "id": id  # From frontend
            }
        elif intent == "query":
            query_demand = subject if subject else (predicate if predicate else (objects[0] if objects else None))
            result["query"] = query_demand

        return result