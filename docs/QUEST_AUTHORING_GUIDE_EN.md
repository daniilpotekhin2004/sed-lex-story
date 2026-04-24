# How to create and fill out a quest using your own scenario and assets

This is a step-by-step instruction for an author who wants to build a quest from scratch:

- according to its plot;
- with your own characters and locations;
- with your own pictures instead of AI sketches;
- with manual checking of the result in the player.

The route to use in most cases is:

1. Create a project.
2. Set the basis of the story in the `Plot Wizard`.
3. Fill the “World Library” with your characters and locations.
4. Collect scenes and branches in the `Graph`.
5. Publish the release.
6. Complete the quest in `Player`.

> If you do not want to use the `Plot Wizard`, you can skip it and follow the scheme: `Project -> World Library -> Graph -> Publication -> Player'.

---

## What to prepare before you start

To make the work go quickly, collect in advance:

- a short synopsis of the story: what the quest is about, who the hero is, what the conflict is;
- list of scenes: what should happen step by step;
- choice points: where the player makes a decision and where it leads;
- characters: names, roles, descriptions, their images `PNG/JPG`;
- locations: names, descriptions, your images `PNG/JPG`;
- if necessary: ​​artifacts, documents, voiceovers.

Practically useful minimum:

- for a character: 1 portrait + 1 full-length image;
- for location: 1 main image + 2-4 references;
- for the scene: title, synopsis, main text, selected location, scene participants.

---

## General screen layout

After creating a project, you will most often work in these screens:

- `Plot Master` - decompose your idea into a structure;
- `Creative development / Library of the world` - create characters and locations;
- `Scenario graphs` - collect scenes and transitions;
- `Publish for player` - release a version;
- `Player` - check the result through the eyes of the player.

![Project Screen](images/quest-guide-ru/02-project-detail.png)

---

## Step 1: Create a project

1. Open the `Projects` page.
2. Click `New Project`.
3. Fill in:
- `Name` - the working name of the quest;
- `Description` - briefly what kind of story it is.
4. Click `Create`.
5. In the project card, click `Open`.

![Creating a project](images/quest-guide-ru/01-create-project.png)

Title recommendation:

- do not name the project too generically like `Test`;
- it is better to use a clear structure: `Court Archive`, `Case of the Missing Evidence`, `Quest 8th grade: evidence`.

---

## Step 2: Set up the story in the Story Wizard

The `Plot Master` is needed not only for AI generation. Even if you do everything manually, it helps:

- structure the plot;
- limit the number of scenes;
- see legal topics in advance;
- make a plan for future assets.

What to do:

1. From the project, open the `Plot Wizard`.
2. In the `Plot input` block, select `Input type`.
3. In the `Plot` field, insert your script synopsis.
4. If necessary, set:
- `Maximum scenes`;
- `Branches`;
- `Answer language`;
- `Legal topics (mandatory)`;
- `Legal topics (optional)`.
5. If you already have entities, add names to:
- `Characters from the library (names)`;
- `Locations from the library (names)`.
6. Click `Create Session`, then run the wizard steps one by one.

![Completing the Plot Wizard](images/quest-guide-ru/03-wizard-input.png)

How to use the wizard's steps in practice:

- `Step 1. Skeleton of the story` - check if there are enough scenes and characters.
- `Step 2. Portraits of the world` - clarify roles and descriptions.
- `Step 3. Scenario slides` - sketch out the setting of the shots.
- `Step 4. Production plan` - understand what assets are really needed.
- `Step 5. Variability` - check where the elections will be.
- `Step 6. Connection map` - check scenes and dependencies.
- `Step 7. Critical audit` - catch logical holes before assembling the graph.

If you already know exactly the structure of the quest, use the wizard as an outline editor, and not as a source of the final text.

---

## Step 3. Add characters with your own images

Open the `Creative Development` or `World Library` project, the `Characters` tab.

### Fast way

If the character has already been invented and you have your own pictures:

1. Click `+ Quick`.
2. Fill out a short card:
- Name;
- description;
- role;
- brief description of appearance;
- voice/manner of speech.
3. Uncheck the 'Generate sketch immediately' checkbox if you want to use only your assets.
4. Click `Create`.

![Quick character creation](images/quest-guide-ru/04-character-quick-create.png)

### When to use `+ Master`

Use `+Master` if you need:

- expand on the visual DNA of the character in more detail;
- record voice, motivation, legal status;
- get a more strict preparation for production.

### How to upload your character pictures

After creating a character, open his card and fill out the visual block:

1. In the top block, click 'Upload portrait'.
2. In the `Reference Package` section, upload at least:
- `Portrait`;
- `Full growth`.
3. If necessary, add additional angles.
4. Save text edits if you changed the description, role or voice.

![Character with his assets](images/quest-guide-ru/05-character-assets.png)

Practical advice:

- if a character must consistently look the same in scenes, do not limit yourself to one portrait;
- minimum for confident work: portrait + full height;
- if the character is minor and rarely appears, you can start with two images and add more later.

---

## Step 4. Add locations with your images

Go to the `Locations` tab.

### Quickly create a location

1. Click `+ Quick`.
2. Fill in:
- `Name`;
- `Description`;
- `Visual description`;
- ``Last name''.
3. If you already have your own pictures, uncheck the “Generate sketch immediately” checkbox.
4. Click `Create`.

![Quick location creation](images/quest-guide-ru/06-location-quick-create.png)

### How to upload your location pictures

On the location card:

1. Click `Upload sketch` or `Upload instead of sketch` for the main image.
2. Download slot references below:
- `Exterior`;
- `Interior`;
- `Detail';
- `Map`.

![Location with its assets](images/quest-guide-ru/07-location-assets.png)

What is the point of slots:

- `Exterior` - general view of the place from the outside;
- `Interior` - main view inside;
- `Detail` is an important fragment that will be useful in the scene;
- `Map` - a diagram of space, if the scene depends on the location of objects.

If you don't have a full set yet, you can start with the main image and gradually fill in the remaining slots.

---

## Step 5. Create a scenario graph

You now have the foundation of the story and the library of the world. The next step is to assemble everything into scenes and transitions.

### Create a graph

1. Return to the project.
2. In the `Scenario graphs` block, click `New graph`.
3. Provide a title and description.
4. Click `Create graph`.

![Create graph](images/quest-guide-ru/08-create-graph.png)

Usually one graph per version of history is enough. It makes sense to create a new graph if you are assembling an alternative structure, and not just editing the current one.

### Complete the scenes

The graph has two operating modes:

- `Editor` - more convenient for sequential writing of scenes;
- `Graph` - more convenient for reviewing branches and transitions.

What to do for each scene:

1. Create a scene.
2. Fill in:
- `Title`;
- ``Synopsis'';
- `Contents`;
- `Scene type` (`History` or `Decision`).
3. In the right panel, select:
- `Legal concepts`;
- `Location';
- ``Frame preset'';
- `Artifacts`, if any.
4. In the `Character Presets` block, link the required characters to the scene.
5. Click 'Save Scene'.

For branching:

1. Make a scene like `Decision`.
2. Create several transitions from it.
3. Label the choices as the player will see them.

After assembly, be sure to click 'Run Validation'.

![Collected history graph](images/quest-guide-ru/09-graph-editor.png)

What is important to check in the column:

- the story has a starting scene;
- clear transitions lead from each “Decision” scene;
- there are no orphan scenes that you can’t get into;
- each scene is associated with the correct location;
- the scenes are linked to exactly those characters who actually participate in the episode.

---

## Step 6. Publish a release for the player

The player does not show the draft graph, but the published release.

What to do:

1. Return to the project card.
2. Find the `Publish for player` block.
3. In the Graph for publication field, select the desired graph.
4. If desired, fill out the `Release Comment`.
5. Click `Publish release`.

![Release publishing panel](images/quest-guide-ru/10-release-panel.png)

Important:

- after edits in the column, you need to publish a new release;
- otherwise the player will show the previous version;
- if you are testing several iterations, it is convenient to leave a short comment on each release.

---

## Step 7. Complete the quest in the player as a player

After publishing, open `Play Story` or go to `Player`.

Check:

- is the order of the scenes correct?
- whether the necessary selections are displayed;
- does the text of the scenes meet expectations;
- are the characters and locations lost?
- Are there any logical dead ends?

![Checking the quest in the player](images/quest-guide-ru/11-player-preview.png)

During the test phase, go through the story at least twice:

- once along the “main” branch;
- the second time on an alternative branch.

This way you will quickly see errors in transitions and inconsistencies in the text.

---

## What can be added after the basic build

When the draft version is already working, you can expand the project:

- `Voice acting for the project` - if you want to approve lines and audio;
- `Artifacts` - if there are documents, evidence, objects in history;
- `Documents` - if you need templates of legal materials;
- `Style Bible` - if the project is large and you need to maintain a single tone.

Best order of operation:

1. First, get the plot, characters, and locations working.
2. Then stabilize the graph and branches.
3. Only after that do voice acting, additional artifacts and cosmetics.

---

## Minimal working scenario without unnecessary complication

If you want to get the first working version as quickly as possible, do this:

1. Create a project.
2. In the Story Wizard, set only the synopsis and scene limit.
3. Create 1-3 characters via `+ Quick`.
4. Upload your character images.
5. Create 1-3 locations using `+ Quick`.
6. Upload your location images.
7. Create 3-5 scenes in a graph.
8. Add one selection point.
9. Publish the release.
10. Go through the story in the player.

This loop produces the first playable version the fastest.

---

## Common mistakes and how to avoid them

### 1. Make too many assets at once

Error:

- the author tries to completely fill out all the characters, all the locations and all the branches before the first check.

Which is better:

- first collect a short working route;
- then expand the library of the world.

### 2. Use beautiful pictures, but don’t tie them to scenes

Error:

- images are loaded into the library, but the location is not selected in the scene and the characters are not linked.

Which is better:

- after each new scene, immediately assign a location and participants.

### 3. Check the draft only in the column

Error:

- in the editor everything looks logical, but in the player the choices or order of scenes are perceived differently.

Which is better:

- check every significant edit in `Player`.

### 4. Forgetting to publish a new release

Error:

- the graph has already been changed, but the player shows the old version.

Which is better:

- after a set of changes, immediately publish a new release.

### 5. Reload the first version

Error:

- too many branches, characters and legal topics in the first draft.

Which is better:

- first one main route and one meaningful fork solution;
- then expansion.

---

## Final checklist before passing the quest

- The project was created and clearly named.
- The Story Master sets the structure of the story.
- Each main character has a card and their own images.
- Each important location has a card and its own images.
- Scenes are collected in a graph.
- Transitions between scenes have been checked.
- Graph validation started.
- Release published.
- The quest was completed in the player along at least two routes.

---

## A short reminder on choosing a mode

Use `+Quickly` if:

- you already know what exactly you are creating;
- you have ready-made pictures;
- you need to quickly collect a work quest.

Use `+Master` if:

- the character or location has not yet been fully thought out;
- you need a more detailed structure;
- you want to prepare the asset closer to the production level.

Use the `Plot Wizard` if:

- the story has not yet been broken down into scenes;
- you need to check the completeness of the plan;
- you need to get a production plan and a connection map.

---

If the next step is needed, it is logical to make a second document: a separate guide only for the “Plot Master” or a separate guide only for the “Graph” with an analysis of branching and typical transition schemes.
