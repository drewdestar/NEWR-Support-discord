const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('unlock')
        .setDescription('Unlock a channel to allow members to send messages')
        .addChannelOption(option =>
            option.setName('channel')
                .setDescription('The channel to unlock (defaults to current channel)')
                .setRequired(false)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ManageChannels),
    
    async execute(interaction, client, config) {
        const channel = interaction.options.getChannel('channel') || interaction.channel;
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.ManageChannels)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to manage channels!', 
                ephemeral: true 
            });
        }
        
        if (!channel.isTextBased()) {
            return interaction.reply({ 
                content: '❌ You can only unlock text channels!', 
                ephemeral: true 
            });
        }
        
        try {
            // Get the @everyone role
            const everyoneRole = interaction.guild.roles.everyone;
            
            // Set permissions to allow SEND_MESSAGES
            await channel.permissionOverwrites.edit(everyoneRole, {
                SendMessages: true
            }, `Channel unlocked by ${interaction.user.tag}`);
            
            const embed = new EmbedBuilder()
                .setColor(0x2ECC71)
                .setTitle('🔓 Channel Unlocked')
                .setDescription(`**${channel.name}** has been unlocked!\nMembers can now send messages in this channel.`)
                .addFields({ name: 'Moderator', value: `${interaction.user.tag}`, inline: true })
                .setTimestamp();
            
            await interaction.reply({ embeds: [embed] });
            
        } catch (error) {
            console.error('Error unlocking channel:', error);
            await interaction.reply({ 
                content: '❌ Failed to unlock the channel! Make sure I have the necessary permissions.', 
                ephemeral: true 
            });
        }
    }
};
