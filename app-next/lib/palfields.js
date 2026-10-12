// lib/palfields.js
// Minimal DedicatedServer settings for Dragonwilds.
// Network/auth keys are managed by the app.
// type: bool | int | float | text | select | tuple

const GROUPS = [
  {
    title: "Server",
    fields: [
      { key: "OwnerId", label: "Owner ID", type: "text", default: "" },
      { key: "ServerName", label: "Server name", type: "text", default: "Runescape Dragonwilds Server" },
      { key: "DefaultWorldName", label: "Default world name", type: "text", default: "My Runescape Dragonwilds World" },
      { key: "AdminPassword", label: "Admin password", type: "text", default: "" },
      { key: "WorldPassword", label: "World password", type: "text", default: "" },
    ],
  },
];

function allFields(){return GROUPS.flatMap(g=>g.fields);}
function defaults(){const d={};for(const f of allFields())d[f.key]=f.default;return d;}
module.exports={GROUPS,allFields,defaults};
