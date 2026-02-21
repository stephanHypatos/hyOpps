import { StepResult } from '../types';

// Simulated delay to mimic real API calls
function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Simulated external IDs
function fakeId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

export async function executeStep(
  stepName: string,
  context: Record<string, unknown>
): Promise<StepResult> {
  // In a real implementation each case would call the actual external API.
  // For the MVP, all auto steps are simulated stubs that succeed immediately.
  await delay(300);

  switch (stepName) {
    case 'clone_metabase_collection': {
      const collectionId = fakeId('mb-col');
      return {
        success: true,
        output: { metabase_collection_id: collectionId },
      };
    }

    case 'create_metabase_group': {
      const groupId = fakeId('mb-grp');
      return {
        success: true,
        output: {
          metabase_group_id: groupId,
          metabase_group_name: `ext-${context.organization_name || 'partner'}`.toLowerCase().replace(/\s+/g, '-'),
        },
      };
    }

    case 'grant_metabase_db_access': {
      return {
        success: true,
        output: { granted: 'true' },
      };
    }

    case 'create_teams_channel': {
      const channelId = fakeId('teams-ch');
      return {
        success: true,
        output: {
          teams_channel_id: channelId,
          teams_channel_name: `ext-${context.organization_name || 'partner'}`.toLowerCase().replace(/\s+/g, '-'),
        },
      };
    }

    case 'create_slack_group': {
      const groupId = fakeId('slack-grp');
      return {
        success: true,
        output: {
          slack_group_id: groupId,
          slack_group_handle: `ext-${context.organization_name || 'partner'}`.toLowerCase().replace(/\s+/g, '-'),
        },
      };
    }

    case 'add_user_to_studio_companies': {
      return {
        success: true,
        output: { added_companies: JSON.stringify(context.selected_studio_company_ids) },
      };
    }

    case 'add_user_to_metabase_group': {
      return {
        success: true,
        output: { metabase_user_id: fakeId('mb-usr') },
      };
    }

    case 'add_user_to_teams_channel': {
      return {
        success: true,
        output: { teams_membership_id: fakeId('teams-mbr') },
      };
    }

    case 'add_user_to_slack_group': {
      return {
        success: true,
        output: { updated: 'true' },
      };
    }

    case 'create_studio_user_company': {
      const studioId = fakeId('studio');
      return {
        success: true,
        output: { studio_user_company_id: studioId },
      };
    }

    case 'send_studio_invite': {
      return {
        success: true,
        output: { invite_sent: 'true', email: String(context.user_email || '') },
      };
    }

    case 'share_documentation': {
      return {
        success: true,
        output: {
          sent_to: String(context.user_email || ''),
          channels: 'email,slack',
        },
      };
    }

    default:
      return {
        success: false,
        error: `Unknown step: ${stepName}`,
      };
  }
}
