from cgitb import text
import networkx as nx
from neo4j import GraphDatabase
from datetime import datetime
import uuid
import json
import difflib
import pandas as pd
from tqdm import tqdm 
import os

class KnowledgeGraph:
    def __init__(self, neo4j_uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.graph = nx.MultiDiGraph()
        self.csv_loaded = False  # Flag to prevent re-import

        try:
            self.driver = GraphDatabase.driver(neo4j_uri, auth=(user, password))
            print("Connected to Neo4j database")
            self.sync_from_neo4j()
            #with self.driver.session() as session:
            #    session.run("MATCH (n) DETACH DELETE n")  # Clear database (optional)
            #    print("Neo4j database cleared")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {str(e)}")
            self.driver = None

    # ---------------------------
    # CSV Import (only once)
    # ---------------------------
    def import_csv_once(self, csv_path):
        if not self.driver:
            print("Neo4j not connected")
            return
        flag_file = "csv_imported.flag"
        if os.path.exists(flag_file):
            print("CSV data already imported, skipping")
            return
        print(f"Importing CSV data from {csv_path} into Neo4j / KnowledgeGraph")
        df = pd.read_csv(csv_path)
        print(f"Total rows in CSV: {len(df)}")
        max_rows = 100  # adjust for how much you want to show

        for i, (_, row) in enumerate(tqdm(df.iterrows(), total=len(df))):
            if i >= max_rows:
                break   
            post_id = str(row['id'])
            author = str(row['author'])
            parent_id = row['Parent']  
            text = str(row['text'])
            
            stance = str(row.get('Stance')) if pd.notna(row.get('Stance')) else 'None'
            sentiment = str(row.get('Sentiment')) if pd.notna(row.get('Sentiment')) else 'None'

            # Author -> Post
            self.add_fact(author, 'POSTED', post_id, src='CSV Import', original_message=text)

            # Only add reply relationships if this is NOT a root post
            if pd.notna(parent_id) and str(parent_id) != '1':
                self.add_fact(post_id, 'REPLIES_TO', str(parent_id), src='CSV Import', original_message=text)

                # Post -> Stance (always add)
            self.add_fact(post_id, 'HAS_STANCE', stance, src='CSV Import', original_message=text)

            # Post -> Sentiment (always add)
            self.add_fact(post_id, 'HAS_SENTIMENT', sentiment, src='CSV Import', original_message=text)

        # Create the flag file to mark CSV as imported
        with open(flag_file, "w") as f:
            f.write("done")

        print("CSV import complete!")
    
    def get_facts_batch(self, skip=0, limit=100):
        """Fetch a batch of facts from Neo4j."""
        if not self.driver:
            return []

        with self.driver.session() as session:
            query = f"""
                MATCH (s:Entity)-[r:REL]->(o:Entity)
                RETURN s.name AS subject, o.name AS object, r.predicate AS predicate,
                       r.created_at AS created_at, r.src AS src,
                       r.original_message AS original_message, r.version AS version
                SKIP {skip} LIMIT {limit}
            """
            results = session.run(query)
            return [dict(record) for record in results]
        
    def sync_from_neo4j(self, batch_size=10, limit=100):
        """Sync data from Neo4j to NetworkX graph in batches to avoid freezing"""
        if not self.driver:
            print("Neo4j driver unavailable, cannot sync")
            return

        skip = 0
        total_edges = 0
        self.graph.clear()  # Clear existing graph once at the start

        try:
            with self.driver.session() as session:
                while True:
                    query = f"""
                        MATCH (s:Entity)-[r:REL]->(o:Entity)
                        RETURN s.name AS subject, o.name AS object, r.predicate AS predicate,
                            r.created_at AS created_at, r.src AS src,
                            r.original_message AS original_message, r.version AS version
                        SKIP {skip} LIMIT {batch_size}
                    """
                    result = session.run(query)
                    records = list(result)

                    if not records:
                        break  # No more records

                    for rec in records:
                        self.graph.add_edge(
                            rec['subject'], 
                            rec['object'], 
                            predicate=rec['predicate'],
                            created_at=rec['created_at'] or 'Unknown',
                            src=rec['src'] or 'Unknown',
                            original_message=rec['original_message'] or 'N/A',
                            version=rec['version'] or 1
                        )

                    total_edges += len(records)
                    skip += batch_size

                    if limit and total_edges >= limit:
                        break

            print(f"Synced {total_edges} triples to in-memory graph")

        except Exception as e:
            print(f"Failed to sync from Neo4j: {str(e)}")

    def log_operation(self, operation_type, details):
        """Log operations (add, update, delete, delete_all) to operation_log.jsonl"""
        log_entry = {
            "operation": operation_type,
            "details": details,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        try:
            with open('operation_log.jsonl', 'a') as f:
                json.dump(log_entry, f, ensure_ascii=False)
                f.write('\n')
            print(f"Logged {operation_type} operation: {details}")
        except Exception as e:
            print(f"Failed to log operation: {str(e)}")

    
    def add_fact(self, subject, predicate, obj, src, original_message):
        # generate unique ID
        fact_id = str(uuid.uuid4())
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # check if triple exists in NetworkX graph
        edge_exists = False
        if subject in self.graph:
            for neighbor, edges in self.graph[subject].items():
                if neighbor == obj:
                    for edge_key, attr in edges.items():
                        if attr['predicate'] == predicate:
                            edge_exists = True
                            print(f"Triple {subject} {predicate} {obj} already exists in memory graph, skipping")
                            return False

        # check if triple exists in Neo4j
        if self.driver and not edge_exists:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (s:Entity {name: $subject})-[r:REL {predicate: $predicate}]->(o:Entity {name: $object})
                        RETURN count(r) AS count
                    """, subject=subject, predicate=predicate, object=obj)
                    count = result.single()['count']
                    if count > 0:
                        print(f"Triple {subject} {predicate} {obj} already exists in Neo4j, skipping")
                        return False
            except Exception as e:
                print(f"Neo4j check failed: {str(e)}")

        # add to NetworkX graph if triple does not exist
        if src == 'Manual':
            original_message = None
            self.graph.add_edge(
                subject, obj,
                predicate=predicate,
                id=fact_id,
                created_at=created_at,
                src=src,
                original_message=original_message,
                version=1
            )

        # add to Neo4j database
        if self.driver:
            try:
                with self.driver.session() as session:
                    session.run("""
                        MERGE (s:Entity {name: $subject})
                        MERGE (o:Entity {name: $object})
                        CREATE (s)-[r:REL {id: $id, predicate: $predicate, created_at: $created_at, src: $src, original_message: $original_message, version: $version}]->(o)
                    """,
                    subject=subject,
                    object=obj,
                    predicate=predicate,
                    id=fact_id,
                    created_at=created_at,
                    src=src,
                    original_message=original_message,
                    version=1
                    )
                print(f"Triple {subject} {predicate} {obj} (ID: {fact_id}) added to memory and Neo4j, created at: {created_at}, source: {src}, version: 1")
                # log the add operation
                self.log_operation("add", {
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj
                })
            except Exception as e:
                print(f"Neo4j add failed: {str(e)}")
                self.graph.remove_edge(subject, obj)
                return False
        else:
            print("Neo4j driver unavailable")

        return True

    def query_by_entity(self, entity):
        facts = []
        fact_keys = set()
        if self.driver:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (s:Entity {name: $entity})-[r:REL]->(o:Entity)
                        RETURN s.name AS subject, r.predicate AS predicate, o.name AS object, r.id AS id, r.created_at AS created_at, r.src AS src, r.original_message AS original_message, r.version AS version
                        ORDER BY r.version DESC
                        LIMIT 50
                    """, entity=entity)
                    for rec in result:
                        triple = (rec['subject'], rec['predicate'], rec['object'])
                        if triple not in fact_keys:
                            fact_keys.add(triple)
                            original_message = rec['original_message'] if rec['original_message'] is not None else 'N/A'
                            facts.append({
                                "id": rec['id'],  # add unique ID
                                "subject": rec['subject'],
                                "predicate": rec['predicate'],
                                "object": rec['object'],
                                "created_at": rec['created_at'] or 'Unknown',
                                "src": rec['src'] or 'Unknown',
                                "original_message": original_message,
                                "version": str(rec['version'] or 1)
                            })
                    print(f"Neo4j query for {entity} successful, found {len(facts)} records")
            except Exception as e:
                print(f"Neo4j query failed: {str(e)}")

        if entity in self.graph:
            for neighbor in self.graph[entity]:
                for key, attr in self.graph[entity][neighbor].items():
                    triple = (entity, attr['predicate'], neighbor)
                    if triple not in fact_keys:
                        fact_keys.add(triple)
                        original_message = attr.get('original_message', 'N/A')
                        facts.append({
                            "id": attr.get('id'),  # add unique ID
                            "subject": entity,
                            "predicate": attr['predicate'],
                            "object": neighbor,
                            "created_at": attr.get('created_at', 'Unknown'),
                            "src": attr.get('src', 'Unknown'),
                            "original_message": original_message,
                            "version": str(attr.get('version', 1))
                        })

        print(f"Found {len(facts)} unique records for entity {entity}")
        return facts

    def query_by_predicate(self, predicate):
        facts = []
        fact_keys = set()
        if self.driver:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (s:Entity)-[r:REL {predicate: $predicate}]->(o:Entity)
                        RETURN s.name AS subject, r.predicate AS predicate, o.name AS object, r.id AS id, r.created_at AS created_at, r.src AS src, r.original_message AS original_message, r.version AS version
                        ORDER BY r.version DESC
                    """, predicate=predicate)
                    for rec in result:
                        triple = (rec['subject'], rec['predicate'], rec['object'])
                        if triple not in fact_keys:
                            fact_keys.add(triple)
                            original_message = rec['original_message'] if rec['original_message'] is not None else 'N/A'
                            facts.append({
                                "id": rec['id'],  #add unique ID
                                "subject": rec['subject'],
                                "predicate": rec['predicate'],
                                "object": rec['object'],
                                "created_at": rec['created_at'] or 'Unknown',
                                "src": rec['src'] or 'Unknown',
                                "original_message": original_message,
                                "version": str(rec['version'] or 1)
                            })
                    print(f"Neo4j query for predicate {predicate} successful, found {len(facts)} records")
            except Exception as e:
                print(f"Neo4j query failed: {str(e)}")

        for subj, obj, attr in self.graph.edges(data=True):
            if attr['predicate'] == predicate:
                triple = (subj, predicate, obj)
                if triple not in fact_keys:
                    fact_keys.add(triple)
                    original_message = attr.get('original_message', 'N/A')
                    facts.append({
                        "id": attr.get('id'),  # add unique ID
                        "subject": subj,
                        "predicate": attr['predicate'],
                        "object": obj,
                        "created_at": attr.get('created_at', 'Unknown'),
                        "src": attr.get('src', 'Unknown'),
                        "original_message": original_message,
                        "version": str(attr.get('version', 1))
                    })

        print(f"Found {len(facts)} unique records for predicate {predicate}")
        return facts
    
    def query_by_object(self, object_name):
        """Query facts where the given name is the object of the triple"""
        facts = []
        fact_keys = set()
        if self.driver:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (s:Entity)-[r:REL]->(o:Entity {name: $object})
                        RETURN s.name AS subject, r.predicate AS predicate, o.name AS object, r.id AS id, r.created_at AS created_at, r.src AS src, r.original_message AS original_message, r.version AS version
                        ORDER BY r.version DESC
                    """, object=object_name)
                    for rec in result:
                        triple = (rec['subject'], rec['predicate'], rec['object'])
                        if triple not in fact_keys:
                            fact_keys.add(triple)
                            original_message = rec['original_message'] if rec['original_message'] is not None else 'N/A'
                            facts.append({
                                "id": rec['id'],
                                "subject": rec['subject'],
                                "predicate": rec['predicate'],
                                "object": rec['object'],
                                "created_at": rec['created_at'] or 'Unknown',
                                "src": rec['src'] or 'Unknown',
                                "original_message": original_message,
                                "version": str(rec['version'] or 1)
                            })
                    print(f"Neo4j query for object {object_name} successful, found {len(facts)} records")
            except Exception as e:
                print(f"Neo4j query failed: {str(e)}")

        for subj in self.graph:
            if object_name in self.graph[subj]:
                for key, attr in self.graph[subj][object_name].items():
                    triple = (subj, attr['predicate'], object_name)
                    if triple not in fact_keys:
                        fact_keys.add(triple)
                        original_message = attr.get('original_message', 'N/A')
                        facts.append({
                            "id": attr.get('id'),
                            "subject": subj,
                            "predicate": attr['predicate'],
                            "object": object_name,
                            "created_at": attr.get('created_at', 'Unknown'),
                            "src": attr.get('src', 'Unknown'),
                            "original_message": original_message,
                            "version": str(attr.get('version', 1))
                        })

        print(f"Found {len(facts)} unique records for object {object_name}")
        return facts
    
    def fuzzy_query_facts(self, keyword, threshold=0.8):
        facts = []
        fact_keys = set()
        if self.driver:
            try:
                with self.driver.session() as session:
                    # Fuzzy search using APOC for nodes and relationships
                    result = session.run("""
                        MATCH (s:Entity)-[r:REL]->(o:Entity)
                        WHERE apoc.text.fuzzyMatch(s.name, $keyword) OR apoc.text.fuzzyMatch(o.name, $keyword) OR apoc.text.fuzzyMatch(r.predicate, $keyword)
                        RETURN s.name AS subject, r.predicate AS predicate, o.name AS object, r.id AS id, r.created_at AS created_at, r.src AS src, r.original_message AS original_message, r.version AS version
                        ORDER BY r.version DESC
                    """, keyword=keyword)
                    for rec in result:
                        triple = (rec['subject'], rec['predicate'], rec['object'])
                        if triple not in fact_keys:
                            fact_keys.add(triple)
                            original_message = rec['original_message'] if rec['original_message'] is not None else 'N/A'
                            facts.append({
                                "id": rec['id'],
                                "subject": rec['subject'],
                                "predicate": rec['predicate'],
                                "object": rec['object'],
                                "created_at": rec['created_at'] or 'Unknown',
                                "src": rec['src'] or 'Unknown',
                                "original_message": original_message,
                                "version": str(rec['version'] or 1)
                            })
                    print(f"Neo4j fuzzy query for {keyword} successful, found {len(facts)} records")
            except Exception as e:
                print(f"Neo4j fuzzy query failed: {str(e)}")

        # Fuzzy search in NetworkX using difflib

        for subj, obj, attr in self.graph.edges(data=True):
            if (
                difflib.SequenceMatcher(None, subj.lower(), keyword.lower()).ratio() >= threshold or
                difflib.SequenceMatcher(None, obj.lower(), keyword.lower()).ratio() >= threshold or
                difflib.SequenceMatcher(None, attr['predicate'].lower(), keyword.lower()).ratio() >= threshold
            ):
                triple = (subj, attr['predicate'], obj)
                if triple not in fact_keys:
                    fact_keys.add(triple)
                    original_message = attr.get('original_message', 'N/A')
                    facts.append({
                        "id": attr.get('id'),
                        "subject": subj,
                        "predicate": attr['predicate'],
                        "object": obj,
                        "created_at": attr.get('created_at', 'Unknown'),
                        "src": attr.get('src', 'Unknown'),
                        "original_message": original_message,
                        "version": str(attr.get('version', 1))
                    })

        print(f"Found {len(facts)} unique fuzzy records for {keyword}")
        return facts




    def get_all_facts(self):
        facts = []
        fact_keys = set()
        if self.driver:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (s:Entity)-[r:REL]->(o:Entity)
                        RETURN s.name AS subject, r.predicate AS predicate, o.name AS object, r.id AS id, r.created_at AS created_at, r.src AS src, r.original_message AS original_message, r.version AS version
                        ORDER BY r.version DESC
                    """)
                    for rec in result:
                        triple = (rec["subject"], rec["predicate"], rec["object"])
                        if triple not in fact_keys:
                            fact_keys.add(triple)
                            original_message = rec["original_message"] if rec["original_message"] is not None else "N/A"
                            facts.append({
                                "id": rec["id"],  # add unique ID
                                "subject": rec["subject"],
                                "predicate": rec["predicate"],
                                "object": rec["object"],
                                "created_at": rec["created_at"] or "Unknown",
                                "src": rec["src"] or "Unknown",
                                "original_message": original_message,
                                "version": str(rec["version"] or 1)
                            })
                    print(f"Neo4j query for all facts successful, found {len(facts)} records")
            except Exception as e:
                print(f"Neo4j query failed: {str(e)}")

        for subj, obj, attr in self.graph.edges(data=True):
            triple = (subj, attr['predicate'], obj)
            if triple not in fact_keys:
                fact_keys.add(triple)
                original_message = attr.get('original_message', 'N/A')
                facts.append({
                    "id": attr.get('id'),  # add unique ID
                    "subject": subj,
                    "predicate": attr['predicate'],
                    "object": obj,
                    "created_at": attr.get('created_at', 'Unknown'),
                    "src": attr.get('src', 'Unknown'),
                    "original_message": original_message,
                    "version": str(attr.get('version', 1))
                })

        print(f"Found {len(facts)} unique records")
        return facts

    def update_fact(self, subject, old_predicate, object, new_predicate, new_src, new_original_message):
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # check if new predicate is same as old
            if new_predicate == old_predicate:
                print(f"New predicate {new_predicate} is same as old predicate {old_predicate}, skipping update")
                return False
            
            try:
                # check if subject and edge exist in NetworkX graph
                if subject not in self.graph:
                    print(f"Node {subject} does not exist in memory graph")
                    return False
                edge_exists = False
                edge_key = None
                old_attributes = None
                for key, attr in self.graph[subject].get(object, {}).items():
                    if attr['predicate'] == old_predicate:
                        edge_exists = True
                        edge_key = key
                        old_attributes = attr
                        break
                if not edge_exists:
                    print(f"Triple {subject} {old_predicate} {object} does not exist in memory graph")
                    return False

                # Save old triple info to JSON file
                old_fact = {
                    "subject": subject,
                    "old_predicate": old_predicate,
                    "object": object,
                    "id": old_attributes.get('id'),
                    "old_created_at": old_attributes.get('created_at', 'Unknown'),
                    "old_src": old_attributes.get('src', 'Unknown'),
                    "old_original_message": old_attributes.get('original_message', 'N/A'),
                    "old_version": old_attributes.get('version', 1),
                    "updated_to": {
                        "new_predicate": new_predicate,
                        "new_object": object,
                        "id": old_attributes.get('id'),
                        "new_created_at": current_time,
                        "new_src": new_src,
                        "new_original_message": new_original_message,
                        "new_version": old_attributes.get('version', 1) + 1
                    },
                    "timestamp": current_time
                }
                try:
                    with open('update_history.jsonl', 'a') as f:
                        json.dump(old_fact, f, ensure_ascii=False)
                        f.write('\n')
                except Exception as e:
                    print(f"Failed to save update history: {str(e)}")

                # update NetworkX graph, inherit original ID
                self.graph.remove_edge(subject, object, edge_key)
                self.graph.add_edge(
                    subject, object,
                    predicate=new_predicate,
                    id=old_attributes.get('id'),
                    created_at=current_time,
                    src=new_src,
                    original_message=new_original_message,
                    version=old_attributes.get('version', 1) + 1
                )
                print(f"Updated {subject} {old_predicate} {object} (ID: {old_attributes.get('id')}) to {subject} {new_predicate} {object} (version: {self.graph[subject][object][0]['version']}) in memory graph")
                # log the update operation
                self.log_operation("update", {
                    "subject": subject,
                    "old_predicate": old_predicate,
                    "object": object,
                    "new_predicate": new_predicate,
                    "id": old_attributes.get('id')
                })
            except Exception as e:
                print(f"Memory graph update failed: {str(e)}")
                return False

            # update Neo4j database
            if self.driver:
                try:
                    with self.driver.session() as session:
                        result = session.run("""
                            MATCH (s:Entity {name: $subject})-[r:REL {predicate: $old_predicate, id: $id}]->(o:Entity {name: $object})
                            DELETE r
                            WITH s, o
                            CREATE (s)-[new_r:REL {id: $id, predicate: $new_predicate, created_at: $current_time, src: $new_src, original_message: $new_original_message, version: $new_version}]->(o)
                            RETURN count(new_r) as count
                        """, 
                        subject=subject, 
                        old_predicate=old_predicate, 
                        object=object, 
                        id=old_attributes.get('id'),
                        new_predicate=new_predicate, 
                        current_time=current_time, 
                        new_src=new_src, 
                        new_original_message=new_original_message,
                        new_version=old_attributes.get('version', 1) + 1
                        )
                        count = result.single()['count']
                        if count == 0:
                            print(f"Triple {subject} {old_predicate} {object} (ID: {old_attributes.get('id')}) not found in Neo4j")
                            return False
                        print(f"Updated {subject} {old_predicate} {object} (ID: {old_attributes.get('id')}) to {subject} {new_predicate} {object} (version: {old_attributes.get('version', 1) + 1}) in Neo4j")
                        # log operation already handled above
                        return True
                except Exception as e:
                    print(f"Neo4j update failed: {str(e)}")
                    return False
            return True


    def get_update_timeline(self, subject, object, id):
        if not id:
            print(f"Missing ID parameter, cannot query timeline for {subject} * {object}")
            return []
        
        timeline = []
        try:
            with open('update_history.jsonl', 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line.strip())
                        # match id, subject, and object
                        if entry['id'] == id and entry['subject'] == subject and entry['object'] == object:
                            timeline.append({
                                "timestamp": entry['timestamp'],
                                "old_predicate": entry['old_predicate'],
                                "new_predicate": entry['updated_to']['new_predicate'],
                                "id": entry['id'],
                                "version": entry['old_version'],
                                "src": entry['updated_to']['new_src'] or 'Unknown',
                                "original_message": entry['updated_to']['new_original_message'] or 'N/A'
                            })
        except FileNotFoundError:
            print("update_history.jsonl not found, skipping history")
        except Exception as e:
            print(f"Failed to query history: {str(e)}")

        current_entry = None
        if subject in self.graph and object in self.graph[object]:
            for key, attr in self.graph[subject][object].items():
                if attr.get('id') == id:
                    current_entry = {
                        "timestamp": attr.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                        "old_predicate": attr['predicate'],
                        "new_predicate": attr['predicate'],
                        "id": attr.get('id'),
                        "version": attr.get('version', 1),
                        "src": attr.get('src', 'Unknown'),
                        "original_message": attr.get('original_message', 'N/A')
                    }
                    break  # take first matching edge
        elif self.driver:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (s:Entity {name: $subject})-[r:REL {id: $id}]->(o:Entity {name: $object})
                        RETURN r.predicate AS predicate, r.id AS id, r.created_at AS created_at, r.src AS src, r.original_message AS original_message, r.version AS version
                        LIMIT 1
                    """, subject=subject, object=object, id=id)
                    record = result.single()
                    if record:
                        current_entry = {
                            "timestamp": record['created_at'] or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "old_predicate": record['predicate'],
                            "new_predicate": record['predicate'],
                            "id": record['id'],
                            "version": record['version'] or 1,
                            "src": record['src'] or 'Unknown',
                            "original_message": record['original_message'] or 'N/A'
                        }
            except Exception as e:
                print(f"Neo4j query for current triple failed: {str(e)}")

        if current_entry:
            timeline.append(current_entry)

        timeline.sort(key=lambda x: x['timestamp'])
        print(f"Timeline query successful, found {len(timeline)} records for {subject} * {object}")
        return timeline

    def delete_fact(self, subject, predicate, object):
        # Check if subject exists
        if subject not in self.graph:
            print(f"Node {subject} does not exist in memory graph")
            return False

        edge_exists = False
        edge_key = None
        for key, attr in self.graph[subject].get(object, {}).items():
            if attr['predicate'] == predicate:
                edge_exists = True
                edge_key = key
                break
        if not edge_exists:
            print(f"Triple {subject} {predicate} {object} does not exist in memory graph")
            return False
        try:
            self.graph.remove_edge(subject, object, edge_key)
            print(f"Triple {subject} {predicate} {object} deleted from memory graph")
            # Log the delete operation
            self.log_operation("delete", {
                "subject": subject,
                "predicate": predicate,
                "object": object
            })
        except Exception as e:
            print(f"Memory graph deletion failed: {str(e)}")
            return False

        if self.driver:
            try:
                with self.driver.session() as session:
                    result = session.run("""
                        MATCH (s:Entity {name: $subject})-[r:REL {predicate: $predicate}]->(o:Entity {name: $object})
                        DELETE r
                        RETURN count(r) as count
                    """, subject=subject, predicate=predicate, object=object)
                    count = result.single()['count']
                    if count == 0:
                        print(f"Triple {subject} {predicate} {object} not found in Neo4j")
                        return False
                    print(f"Triple {subject} {predicate} {object} deleted from Neo4j")
                    # Log operation already handled above
                    return True
            except Exception as e:
                print(f"Neo4j deletion failed: {str(e)}")
                return False
        return True

    
    def delete_all_facts(self):
        try:
            # Clear NetworkX graph
            self.graph.clear()
            print("Memory graph cleared")
            # Log the delete_all operation
            self.log_operation("delete_all", {"description": "All facts deleted from the knowledge graph"})
        except Exception as e:
            print(f"Memory graph clear failed: {str(e)}")
            return False

        # Clear Neo4j database
        if self.driver:
            try:
                with self.driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
                    print("Neo4j database cleared")
                    # Log operation already handled above
            except Exception as e:
                print(f"Neo4j clear failed: {str(e)}")
                return False

        # Clear update_history.jsonl
        try:
            with open('update_history.jsonl', 'w') as f:
                f.truncate(0)
            print("Update history log cleared")
        except Exception as e:
            print(f"Failed to clear update history log: {str(e)}")
            return False

        return True

    def close(self):
        if self.driver:
            self.driver.close()
            print("Neo4j connection closed")