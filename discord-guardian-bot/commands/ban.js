const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('ban')
        .setDescription('Ban a user from the server')
        .addUserOption(option =>
            option.setName('user')
                .setDescription('The user to ban')
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName('reason')
                .setDescription('Reason for the ban')
                .setRequired(false)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.BanMembers),
    
    async execute(interaction, client, config) {
        const user = interaction.options.getUser('user');
        const reason = interaction.options.getString('reason') || 'No reason provided';
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.BanMembers)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to ban users!', 
                ephemeral: true 
            });
        }
        
        // Check if user is trying to ban themselves or someone with higher role
        const member = await interaction.guild.members.fetch(user.id).catch(() => null);
        
        if (!member) {
            return interaction.reply({ 
                content: '❌ User not found in this server!', 
                ephemeral: true 
            });
        }
        
        if (member.id === interaction.user.id) {
            return interaction.reply({ 
                content: '❌ You cannot ban yourself!', 
                ephemeral: true 
            });
        }
        
        if (member.roles.highest.position >= interaction.member.roles.highest.position) {
            return interaction.reply({ 
                content: '❌ You cannot ban someone with a higher or equal role!', 
                ephemeral: true 
            });
        }
        
        if (!member.bannable) {
            return interaction.reply({ 
                content: '❌ I cannot ban this user! They might have higher permissions.', 
                ephemeral: true 
            });
        }
        
        try {
            await member.ban({ reason: `${reason} | Banned by ${interaction.user.tag}` });
            
            const embed = new EmbedBuilder()
                .setColor(0xFF0000)
                .setTitle('🔨 User Banned')
                .addFields(
                    { name: 'User', value: `${user.tag} (${user.id})`, inline: true },
                    { name: 'Moderator', value: `${interaction.user.tag}`, inline: true },
                    { name: 'Reason', value: reason, inline: false }
                )
                .setTimestamp()
                .setFooter({ text: `ID: ${user.id}` });
            
            await interaction.reply({ embeds: [embed] });
            
            // Log the action
            await logAction(interaction.guild, '🔨 Ban', `User: ${user.tag}\nModerator: ${interaction.user.tag}\nReason: ${reason}`, interaction.user);
            
        } catch (error) {
            console.error('Error banning user:', error);
            await interaction.reply({ 
                content: '❌ Failed to ban the user! Make sure I have the necessary permissions.', 
                ephemeral: true 
            });
        }
    }
};

// Helper function for logging (will be available from main file)
async function logAction(guild, action, details, user) {
    // This will be handled by the main index.js file
    // Just a placeholder to prevent errors
}
