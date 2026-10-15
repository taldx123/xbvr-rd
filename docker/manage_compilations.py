#!/usr/bin/env python3
"""
manage_compilations.py
Utility to identify and tag compilation scenes in XBVR.
Supports Dry-Run scan, High-Confidence Auto-Tagging, and Interactive Review.
"""

import sys
import subprocess
import re
import os
import json

# Terminal color codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_GRAY = "\033[90m"


def run_sql(db_user, db_pass, db_name, query, skip_columns=True):
    """Executes a SQL query inside the xbvr-mariadb container."""
    cmd = [
        "docker", "exec", "xbvr-mariadb", "mariadb",
        f"-u{db_user}", f"-p{db_pass}", db_name
    ]
    if skip_columns:
        cmd.append("--skip-column-names")
    cmd.extend(["-e", query])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Database query failed: {res.stderr.strip()}")
    return res.stdout


def fetch_candidates(db_user, db_pass, db_name):
    """
    Fetches candidate scenes that might be compilations but do NOT have
    the tag_group:compilations tag (tag_id = 2239).
    Scans all scenes; matching physical files from the `files` table are linked if present.
    """
    query = """
    SELECT 
      s.id, 
      s.scene_id, 
      REPLACE(REPLACE(IFNULL(s.site, ''), '\r', ' '), '\n', ' '), 
      REPLACE(REPLACE(IFNULL(s.title, ''), '\r', ' '), '\n', ' '), 
      s.duration, 
      REPLACE(REPLACE(IFNULL(s.synopsis, ''), '\r', ' '), '\n', ' '), 
      REPLACE(REPLACE(IFNULL(s.filenames_arr, ''), '\r', ' '), '\n', ' '),
      (SELECT COUNT(DISTINCT sc.actor_id) FROM scene_cast sc WHERE sc.scene_id = s.id) as cast_cnt,
      IFNULL((SELECT GROUP_CONCAT(t.name) FROM scene_tags st JOIN tags t ON t.id = st.tag_id WHERE st.scene_id = s.id), '') as tags,
      COUNT(DISTINCT f.id) as file_cnt,
      IFNULL(GROUP_CONCAT(DISTINCT REPLACE(REPLACE(f.filename, '\r', ' '), '\n', ' ') SEPARATOR ';;'), '') as filenames
    FROM scenes s
    LEFT JOIN files f ON f.scene_id = s.id
    WHERE s.deleted_at IS NULL
      AND s.id NOT IN (SELECT scene_id FROM scene_tags WHERE tag_id = 2239)
      AND (
        s.title LIKE '%compilat%'
        OR s.title LIKE '%best of%'
        OR s.title LIKE '%Best %Vol%'
        OR s.title LIKE '%Best %Part%'
        OR s.title LIKE '%anthology%'
        OR s.title LIKE '%megamix%'
        OR s.title LIKE '%mashup%'
        OR s.title LIKE '%supercut%'
        OR s.title LIKE '%pleasure pack%'
        OR s.title LIKE '%pack vol%'
        OR s.synopsis LIKE '%compilation%'
        OR s.filenames_arr LIKE '%compilat%'
        OR f.filename LIKE '%compilat%'
        OR s.id IN (
          SELECT sc.scene_id FROM scene_cast sc GROUP BY sc.scene_id HAVING COUNT(DISTINCT sc.actor_id) >= 7
        )
      )
    GROUP BY s.id;
    """
    raw_output = run_sql(db_user, db_pass, db_name, query)
    lines = [line.split("\t") for line in raw_output.strip().split("\n") if line.strip()]

    tier1 = []
    tier2 = []

    for row in lines:
        if len(row) < 11:
            row = (row + [""] * 11)[:11]
        sid, scene_id, site, title, duration_str, synopsis, filenames_arr_str, cast_cnt_str, tags_str, f_cnt_str, f_names = row
        cast_cnt = int(cast_cnt_str) if cast_cnt_str.isdigit() else 0
        duration = int(duration_str) if duration_str.isdigit() else 0
        file_cnt = int(f_cnt_str) if f_cnt_str.isdigit() else 0
        files = [f.strip() for f in f_names.split(";;") if f.strip()]
        tags = set(t.strip().lower() for t in tags_str.split(",") if t.strip())

        reasons = []

        # --- Tier 1 Detection Rules (100% High Confidence) ---
        # 1. Word "compilation" in title (handles scraper typos like 'complilation')
        if re.search(r"\b(comp[li]*lation|compilations)\b", title, re.IGNORECASE):
            reasons.append("Title: 'Compilation'")

        # 2. Franchise volume patterns: Best ... (Adventures|Moments|Compilation|Highlights|Masterpieces) ... (Vol|Volume|Part)
        if re.search(r"\bBest\b.*\b(Adventures|Moments|Compilation|Highlights|Masterpieces)\b.*\b(Vol|Volume|Part)\b", title, re.IGNORECASE):
            reasons.append("Title: Franchise Volume (e.g. Best ... Vol)")
        elif re.search(r"\bMasterpieces\b.*\b(Vol|Volume)\b", title, re.IGNORECASE):
            reasons.append("Title: Franchise Volume (Masterpieces Vol)")

        # 3. Explicit compilation phrases in synopsis
        if re.search(r"\b(this|a|bonus)\s+compilation\b|compilation\s+(video|movie|release|of)|best\s+scenes\s+compilation", synopsis, re.IGNORECASE):
            reasons.append("Synopsis: Explicit compilation")

        # 4. Other definitive digest tokens
        if re.search(r"\b(anthology|megamix|mashup|supercut)\b", title, re.IGNORECASE):
            reasons.append("Title: Digest/Mashup keyword")

        # 5. Pack series titles
        if re.search(r"\b(pack\s+vol|pleasure\s+pack)\b", title, re.IGNORECASE):
            reasons.append("Title: Series Pack")

        # 6. Filename pattern (from physical files table or studio filenames)
        if any(re.search(r"(_compilat|_anthology_|_megamix_)", f, re.IGNORECASE) for f in files) or (filenames_arr_str and re.search(r"(_compilat|_anthology_|_megamix_)", filenames_arr_str, re.IGNORECASE)):
            reasons.append("Filename: Compilation pattern")

        candidate = {
            "id": int(sid),
            "scene_id": scene_id,
            "site": site,
            "title": title,
            "duration": duration,
            "cast_cnt": cast_cnt,
            "files": files,
            "reasons": reasons
        }

        if reasons:
            tier1.append(candidate)
        else:
            # --- Tier 2 Detection Rules (Review Candidates) ---
            tier2_reasons = []

            # Multi-actor or volume "Best of" releases (e.g. "Best of Solo" or "Best of Stepdaughters Part 1")
            # Note: Single-performer titles like "The Best of Betzz" or "The Best of Spain" (cast_cnt=1, no volume) are excluded.
            if re.search(r"^(the\s+)?best\s+of\b", title, re.IGNORECASE) and not re.search(r"best\s+of\s+friends|get\s+the\s+best\s+of", title, re.IGNORECASE):
                if cast_cnt >= 2 or re.search(r"\b(vol|volume|part)\b", title, re.IGNORECASE):
                    tier2_reasons.append(f"'Best of' pattern ({cast_cnt} performers / volume)")

            # High cast count heuristic (excluding explicit group scene tags)
            if cast_cnt >= 7 and not tags.intersection({"orgy", "gangbang", "party"}):
                tier2_reasons.append(f"High cast count ({cast_cnt} actors)")

            if tier2_reasons:
                candidate["reasons"] = tier2_reasons
                tier2.append(candidate)

    return tier1, tier2


def print_table(candidates, title_header):
    """Prints a formatted ASCII table of candidates."""
    print(f"\n{C_BOLD}{C_CYAN}=== {title_header} ({len(candidates)} scenes) ==={C_RESET}")
    if not candidates:
        print(f"  {C_GRAY}None found.{C_RESET}\n")
        return

    print(f"  {'ID':<7} {'Site':<18} {'Dur':<8} {'Title':<36} {'File(s)':<40} {'Reason'}")
    print(f"  {'-'*6} {'-'*17} {'-'*7} {'-'*35} {'-'*39} {'-'*28}")

    for c in candidates:
        cid = str(c["id"])
        site = (c["site"][:16] + "..") if len(c["site"]) > 17 else c["site"]
        dur = f"{c['duration']} min" if c["duration"] > 0 else "N/A"
        title = (c["title"][:34] + "..") if len(c["title"]) > 35 else c["title"]

        # Format real pointing files from files table, or None if no match
        if c["files"]:
            first_file = c["files"][0]
            if len(c["files"]) > 1:
                display_file = f"({len(c['files'])}) {first_file}"
            else:
                display_file = first_file
            file_str = (display_file[:38] + "..") if len(display_file) > 39 else display_file
            file_colored = f"{C_GREEN}{file_str:<40}{C_RESET}"
        else:
            file_colored = f"{C_GRAY}{'None':<40}{C_RESET}"

        reason = ", ".join(c["reasons"])
        print(f"  {cid:<7} {site:<18} {dur:<8} {title:<36} {file_colored} {C_YELLOW}{reason}{C_RESET}")
    print()


def apply_compilation_tags(db_user, db_pass, db_name, candidate_list):
    """Applies the 'compilation' tag to the specified scenes, logging actions and updating tag groups."""
    if not candidate_list:
        print(f"{C_YELLOW}No scenes selected for tagging.{C_RESET}")
        return

    print(f"\n{C_CYAN}Ensuring 'compilation' tag exists...{C_RESET}")
    tag_id_out = run_sql(
        db_user, db_pass, db_name,
        "SELECT id FROM tags WHERE name = 'compilation' LIMIT 1;"
    ).strip()

    if not tag_id_out or not tag_id_out.isdigit():
        print(f"Creating 'compilation' tag record...")
        run_sql(
            db_user, db_pass, db_name,
            "INSERT INTO tags (name, clean, count) VALUES ('compilation', 'compilation', 0);"
        )
        tag_id_out = run_sql(
            db_user, db_pass, db_name,
            "SELECT id FROM tags WHERE name = 'compilation' LIMIT 1;"
        ).strip()

    tag_id = int(tag_id_out)
    print(f"Using 'compilation' tag ID: {C_GREEN}{tag_id}{C_RESET}")

    total = len(candidate_list)
    print(f"Applying tag and action entries for {total} scenes...")

    # Build batch SQL for speed and atomicity
    sql_statements = []
    for c in candidate_list:
        db_id = c["id"]
        scene_id = c["scene_id"].replace("'", "''")

        # 1. Add relation to scene_tags
        sql_statements.append(f"INSERT IGNORE INTO scene_tags (scene_id, tag_id) VALUES ({db_id}, {tag_id});")
        # 2. Add action entry so ReapplyEdits preserves it across rescrapes
        sql_statements.append(
            f"INSERT INTO actions (scene_id, action_type, changed_column, new_value) "
            f"VALUES ('{scene_id}', 'edit', 'tags', '+compilation');"
        )
        # 3. Mark scene as having edits applied
        sql_statements.append(f"UPDATE scenes SET edits_applied = 1 WHERE id = {db_id};")

    # Execute scene updates
    batch_query = "\n".join(sql_statements)
    run_sql(db_user, db_pass, db_name, batch_query, skip_columns=False)

    print(f"{C_GREEN}Successfully tagged {total} scenes!{C_RESET}")

    # Synchronize Tag Group
    refresh_tag_group(db_user, db_pass, db_name)


def refresh_tag_group(db_user, db_pass, db_name):
    """Executes the XBVR Tag Group update query to populate 'tag group:compilations'."""
    print(f"\n{C_CYAN}Propagating tag group:compilations across scenes...{C_RESET}")

    update_query = """
    INSERT INTO scene_tags (scene_id, tag_id)
    SELECT DISTINCT st.scene_id, tg.tag_group_tag_id 
    FROM tag_groups tg
    JOIN tag_group_tags tgt ON tgt.tag_group_id = tg.id
    JOIN scene_tags st ON st.tag_id = tgt.tag_id 
    LEFT JOIN scene_tags st2 ON st2.scene_id = st.scene_id AND st2.tag_id = tg.tag_group_tag_id
    WHERE tg.name = 'compilations' AND st2.tag_id IS NULL;

    UPDATE tags t
    SET count = (
        SELECT COUNT(st.scene_id)
        FROM scene_tags st
        JOIN scenes s ON s.id = st.scene_id AND s.deleted_at IS NULL
        WHERE st.tag_id = t.id
    )
    WHERE t.id IN (
        SELECT DISTINCT tgt.tag_id FROM tag_groups tg JOIN tag_group_tags tgt ON tgt.tag_group_id = tg.id WHERE tg.name = 'compilations'
        UNION 
        SELECT tg.tag_group_tag_id FROM tag_groups tg WHERE tg.name = 'compilations'
    );
    """
    run_sql(db_user, db_pass, db_name, update_query, skip_columns=False)

    new_count = run_sql(
        db_user, db_pass, db_name,
        "SELECT count FROM tags WHERE name = 'tag group:compilations' LIMIT 1;"
    ).strip()
    print(f"{C_BOLD}{C_GREEN}Done! Total scenes in 'tag group:compilations': {new_count}{C_RESET}\n")


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 manage_compilations.py <db_user> <db_pass> <db_name> [--dry-run|--auto|--interactive|--refresh]")
        sys.exit(1)

    db_user = sys.argv[1]
    db_pass = sys.argv[2]
    db_name = sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else "--dry-run"

    print(f"\n{C_BOLD}===================================================={C_RESET}")
    print(f"{C_BOLD}          XBVR COMPILATION SCENE MANAGER            {C_RESET}")
    print(f"{C_BOLD}===================================================={C_RESET}")

    if mode == "--refresh":
        refresh_tag_group(db_user, db_pass, db_name)
        return

    print(f"Scanning library for untagged compilation scenes...")
    tier1, tier2 = fetch_candidates(db_user, db_pass, db_name)

    if mode == "--dry-run":
        print_table(tier1, "Tier 1: High-Confidence Candidates (Title / Synopsis / Metadata)")
        print_table(tier2, "Tier 2: Review Candidates (Cast Count >= 7 & Series Digests)")
        print(f"{C_BOLD}Scan complete (Dry-Run: No database modifications made).{C_RESET}")
        print(f"  Tier 1 high-confidence matches: {C_GREEN}{len(tier1)}{C_RESET}")
        print(f"  Tier 2 review candidates:      {C_YELLOW}{len(tier2)}{C_RESET}\n")

    elif mode == "--auto":
        print_table(tier1, "Tier 1: High-Confidence Candidates to Tag")
        if not tier1:
            print(f"{C_GREEN}No untagged Tier 1 compilations found. Your library is up to date!{C_RESET}\n")
            return

        confirm = input(f"{C_BOLD}Apply 'compilation' tag to all {len(tier1)} Tier 1 scenes? [y/N]: {C_RESET}").strip().lower()
        if confirm == 'y':
            apply_compilation_tags(db_user, db_pass, db_name, tier1)
        else:
            print(f"{C_YELLOW}Aborted by user.{C_RESET}\n")

    elif mode == "--interactive":
        all_candidates = tier1 + tier2
        print_table(tier1, "Tier 1 Candidates")
        print_table(tier2, "Tier 2 Candidates")

        if not all_candidates:
            print(f"{C_GREEN}No untagged compilation candidates found.{C_RESET}\n")
            return

        to_tag = []
        print(f"\n{C_BOLD}Starting Interactive Review ({len(all_candidates)} candidates):{C_RESET}")
        print(f"{C_GRAY}Commands: [y] Yes / [n] No (default) / [a] Tag all remaining / [q] Quit{C_RESET}\n")

        for idx, c in enumerate(all_candidates, 1):
            reason_str = ", ".join(c["reasons"])
            if c["files"]:
                if len(c["files"]) > 1:
                    file_info = f"  Files ({len(c['files'])} in files table):\n" + "\n".join(f"    - {f}" for f in c["files"])
                else:
                    file_info = f"  File: {c['files'][0]}"
            else:
                file_info = "  File: None"

            prompt = (
                f"[{idx}/{len(all_candidates)}] ID:{c['id']} | {c['site']} | {c['title']} ({c['duration']}m)\n"
                f"{file_info}\n"
                f"  Reason: {C_YELLOW}{reason_str}{C_RESET}\n"
                f"  Tag as compilation? [y/N/a/q]: "
            )
            ans = input(prompt).strip().lower()
            if ans == 'y':
                to_tag.append(c)
                print(f"  -> {C_GREEN}Marked for tagging{C_RESET}\n")
            elif ans == 'a':
                to_tag.extend(all_candidates[idx-1:])
                print(f"  -> {C_GREEN}Marked all remaining {len(all_candidates) - idx + 1} scenes for tagging{C_RESET}\n")
                break
            elif ans == 'q':
                print(f"  -> {C_YELLOW}Exiting review loop{C_RESET}\n")
                break
            else:
                print(f"  -> {C_GRAY}Skipped{C_RESET}\n")

        if to_tag:
            apply_confirm = input(f"Ready to apply tag to {len(to_tag)} approved scenes? [y/N]: ").strip().lower()
            if apply_confirm == 'y':
                apply_compilation_tags(db_user, db_pass, db_name, to_tag)
            else:
                print(f"{C_YELLOW}Aborted.{C_RESET}\n")
        else:
            print(f"No scenes were marked for tagging.\n")

    else:
        print(f"{C_RED}Unknown mode: {mode}{C_RESET}")


if __name__ == "__main__":
    main()
