import React from "react";

import type { SubstringMapping } from "@services/types/questions";

interface CharacterMappingTableProps {
  mappings: SubstringMapping[];
}

const CharacterMappingTable: React.FC<CharacterMappingTableProps> = ({ mappings }) => (
  <table className="character-mapping-table">
    <thead>
      <tr>
        <th>Original</th>
        <th>Replacement</th>
        <th>Context</th>
        <th>Effectiveness</th>
      </tr>
    </thead>
    <tbody>
      {mappings.map((mapping, index) => (
        <tr key={`${mapping.original}-${index}`}>
          <td>{mapping.original}</td>
          <td>{mapping.replacement}</td>
          <td>{mapping.context}</td>
          <td>{mapping.effectiveness_score ? `${(mapping.effectiveness_score * 100).toFixed(0)}%` : "—"}</td>
        </tr>
      ))}
    </tbody>
  </table>
);

export default CharacterMappingTable;
